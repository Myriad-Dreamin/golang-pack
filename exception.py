class GolangToolInvokeError(Exception):
    code: int
    msg: str

    def __init__(self, *_, code, error_dump):
        self.code = code
        self.msg = error_dump

    def __str__(self):
        return f'exit with {self.code}, msg: {self.msg}'
