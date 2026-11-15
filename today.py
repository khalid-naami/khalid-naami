import os
import time
import hashlib
import requests
from lxml import etree

# Fine-grained or classic personal access token stored in GitHub Actions secrets:
# Account/Repository read permissions for repositories, commits, and followers.
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN', '').strip()
if not ACCESS_TOKEN:
    raise RuntimeError('ACCESS_TOKEN environment variable is required')

HEADERS = {'authorization': 'token ' + ACCESS_TOKEN}
USER_NAME = os.environ.get('USER_NAME') or 'khalid-naami'
QUERY_COUNT = {
    'user_getter': 0,
    'follower_getter': 0,
    'graph_repos_stars': 0,
    'recursive_loc': 0,
    'loc_query': 0,
}


def simple_request(func_name, query, variables):
    """
    Executes a GraphQL POST request and returns the response, or raises on HTTP/GraphQL errors.
    """
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
        timeout=30,
    )
    if request.status_code == 200:
        payload = request.json()
        if 'errors' in payload and not payload.get('data'):
            raise Exception(func_name, 'GraphQL errors:', payload['errors'], QUERY_COUNT)
        return request
    raise Exception(func_name, 'has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    """
    Uses GitHub's GraphQL v4 API to return total repository or star counts.
    """
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    repos = request.json()['data']['user']['repositories']
    if count_type == 'repos':
        return repos['totalCount']
    if count_type == 'stars':
        total_stars = stars_counter(repos['edges'])
        while repos['pageInfo']['hasNextPage']:
            query_count('graph_repos_stars')
            variables['cursor'] = repos['pageInfo']['endCursor']
            request = simple_request(graph_repos_stars.__name__, query, variables)
            repos = request.json()['data']['user']['repositories']
            total_stars += stars_counter(repos['edges'])
        return total_stars
    return 0


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from a repository at a time.
    """
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
        timeout=30,
    )
    if request.status_code == 200:
        repo_data = request.json().get('data', {}).get('repository')
        if repo_data and repo_data.get('defaultBranchRef') is not None:
            return loc_counter_one_repo(
                owner,
                repo_name,
                data,
                cache_comment,
                repo_data['defaultBranchRef']['target']['history'],
                addition_total,
                deletion_total,
                my_commits,
            )
        return 0, 0, 0
    force_close_file(data, cache_comment)
    if request.status_code == 403:
        raise Exception("Too many requests in a short amount of time!\nYou've hit the anti-abuse rate limit!")
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text, QUERY_COUNT)


def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    """
    Recursively counts additions, deletions, and commits authored by OWNER_ID across repository history.
    """
    for node in history['edges']:
        author = node['node'].get('author')
        if author and author.get('user') == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    return recursive_loc(
        owner,
        repo_name,
        data,
        cache_comment,
        addition_total,
        deletion_total,
        my_commits,
        history['pageInfo']['endCursor'],
    )


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=None):
    """
    Queries all accessible repositories (60 at a time to avoid GraphQL timeouts) and computes LOC totals.
    """
    if edges is None:
        edges = []
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef {
                                target {
                                    ... on Commit {
                                        history {
                                            totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    repos = request.json()['data']['user']['repositories']
    if repos['pageInfo']['hasNextPage']:
        edges += repos['edges']
        return loc_query(owner_affiliation, comment_size, force_cache, repos['pageInfo']['endCursor'], edges)
    return cache_builder(edges + repos['edges'], comment_size, force_cache)


def cache_filename():
    """
    Returns the per-user cache file path under cache/.
    """
    os.makedirs('cache', exist_ok=True)
    return 'cache/' + hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt'


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository against the cache and updates LOC counts when commit counts change.
    """
    cached = True
    filename = cache_filename()
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            for _ in range(comment_size):
                data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w', encoding='utf-8') as f:
            f.writelines(data)

    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r', encoding='utf-8') as f:
            data = f.readlines()

    cache_comment = data[:comment_size]
    data = data[comment_size:]
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        name_with_owner = edges[index]['node']['nameWithOwner']
        if repo_hash == hashlib.sha256(name_with_owner.encode('utf-8')).hexdigest():
            try:
                total_commits = edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']
                if int(commit_count) != total_commits:
                    owner, repo_name = name_with_owner.split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = f'{repo_hash} {total_commits} {loc[2]} {loc[0]} {loc[1]}\n'
            except TypeError:
                data[index] = f'{repo_hash} 0 0 0 0\n'
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    """
    Rebuilds the cache file skeleton when the repository list size changes or on first run.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        data = f.readlines()[:comment_size] if comment_size > 0 else []
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(data)
        for node in edges:
            repo_hash = hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest()
            f.write(f'{repo_hash} 0 0 0 0\n')


def force_close_file(data, cache_comment):
    """
    Saves partial cache data before raising an exception on API errors.
    """
    filename = cache_filename()
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. Partial data saved to', filename)


def stars_counter(data):
    """
    Counts total stargazers across repository edges.
    """
    total_stars = 0
    for node in data:
        total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def svg_overwrite(filename, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data):
    """
    Parses an SVG file and updates GitHub stats elements and their dot padding.
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, 'commit_data', commit_data, 23)
    justify_format(root, 'star_data', star_data, 14)
    justify_format(root, 'repo_data', repo_data, 6)
    justify_format(root, 'contrib_data', contrib_data)
    justify_format(root, 'follower_data', follower_data, 10)
    justify_format(root, 'loc_data', loc_data[2], 9)
    justify_format(root, 'loc_add', loc_data[0])
    justify_format(root, 'loc_del', loc_data[1], dots=False)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def justify_format(root, element_id, new_text, length=0, dots=True):
    """
    Updates element text and adjusts the preceding *_dots element to preserve 60-char line alignment.
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    if not dots:
        find_and_replace(root, f'{element_id}_dots', '')
        return
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f'{element_id}_dots', dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds an SVG element by id and sets its text content.
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size):
    """
    Sums authored commits from the repository cache file.
    """
    total_commits = 0
    filename = cache_filename()
    with open(filename, 'r', encoding='utf-8') as f:
        data = f.readlines()[comment_size:]
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    """
    Returns the GraphQL node ID dict and creation timestamp of the user.
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    request = simple_request(user_getter.__name__, query, {'login': username})
    user = request.json()['data']['user']
    return {'id': user['id']}, user['createdAt']


def follower_getter(username):
    """
    Returns the follower count of the user.
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    """
    Increments the GraphQL API call counter for the given query type.
    """
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    """
    Executes funct(*args) and returns (result, elapsed_seconds).
    """
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    """
    Prints a formatted execution timing line.
    """
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


if __name__ == '__main__':
    print('Calculation times:')
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)

    total_loc, loc_time = perf_counter(loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7)
    formatter('LOC (cached)', loc_time) if total_loc[-1] else formatter('LOC (no cache)', loc_time)

    commit_data, commit_time = perf_counter(commit_counter, 7)
    formatter('commits', commit_time)

    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    formatter('stars', star_time)

    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    formatter('repos', repo_time)

    contrib_data, contrib_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    formatter('contributions', contrib_time)

    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)
    formatter('followers', follower_time)

    for index in range(len(total_loc) - 1):
        total_loc[index] = '{:,}'.format(total_loc[index])

    svg_overwrite('dark_mode.svg', commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:-1])
    svg_overwrite('light_mode.svg', commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:-1])

    total_time = user_time + loc_time + commit_time + star_time + repo_time + contrib_time + follower_time
    print('{:<23}'.format('Total function time:'), '{:>11}'.format('%.4f' % total_time), ' s', sep='')
    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items():
        print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
