"""Project lookup endpoint (post-fix for issue #123). Self-contained + importable."""


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


def get_project(project_id, cache):
    project = cache.get(project_id)
    if project is None:
        # FIX(#123): a cache miss for a missing project must 404, not 500.
        return Response(404, {"error": "project not found"})
    return Response(200, project)
