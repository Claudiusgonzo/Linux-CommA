from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch, helpers
from pygit2 import (
    Repository,
    discover_repository,
    clone_repository,
    GIT_SORT_TOPOLOGICAL,
)


def get_patches():
    repos = [
        (
            "linux-mainline",
            "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
            "/tmp/linux-mainline",
        ),
        ("openSUSE", "https://github.com/openSUSE/kernel.git", "/tmp/openSUSE"),
    ]
    for name, url, path in repos:
        if discover_repository(path):
            repo = Repository(path)
            repo.remotes["origin"].fetch()
        else:
            repo = clone_repository(url, path, bare=True)

        walker = repo.walk(repo.head.target, GIT_SORT_TOPOLOGICAL)

        walker.hide(repo["8834f5600cf3c8db365e18a3d5cac2c2780c81e5"].id)
        for commit in walker:
            author_time = datetime.fromtimestamp(
                float(commit.author.time),
                timezone(timedelta(minutes=commit.author.offset)),
            ).isoformat()
            commit_time = datetime.fromtimestamp(
                float(commit.commit_time),
                timezone(timedelta(minutes=commit.commit_time_offset)),
            ).isoformat()
            diff = repo.diff(commit.parents[0], commit)
            files = [d.new_file.path for d in diff.deltas]
            yield {
                "_index": "commits",
                "_type": "document",
                "_id": commit.hex,
                "doc": {
                    "repo": name,
                    "commit_id": commit.hex,
                    "patch_id": diff.patchid.hex,
                    "parent_ids": [p.hex for p in commit.parents],
                    "merge": len(commit.parents) > 1,
                    "author": {
                        "name": commit.author.name,
                        "email": commit.author.email,
                        "time": author_time,
                    },
                    "committer": {
                        "name": commit.committer.name,
                        "email": commit.committer.email,
                        "time": commit_time,
                    },
                    "summary": commit.message.splitlines()[0],
                    # TODO: Split out Signed-off-by etc.
                    "message": "\n".join(commit.message.splitlines()[2:]),
                    "files": files,
                    # "hunks": [
                    #     {
                    #         "header": h.header,
                    #         "lines": [
                    #             l.content.strip()
                    #             for l in h.lines
                    #             if not l.content.isspace()
                    #         ],
                    #     }
                    #     for d in diff
                    #     for h in d.hunks
                    # ],
                },
            }


elastic = Elasticsearch(sniff_on_start=True)
print(elastic.info())
print("Indexing commits...")
for success, info in helpers.parallel_bulk(elastic, get_patches(), thread_count=8):
    if not success:
        print(info)
