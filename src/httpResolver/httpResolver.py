from enum import Enum
from typing import Optional, Callable

from src.httpResolver.httpBodyResolver import BodySetting
from src.httpResolver.httpHeaderResolver import ParsedHeaders, HeaderResolver

# RFC 7230 token: 1*tchar
# tchar = "!" / "#" / "$" / "%" / "&" / "'" / "*"
#       / "+" / "-" / "." / "^" / "_" / "`" / "|" / "~"
#       / DIGIT / ALPHA
_ALLOWED_TCHAR = set(b"!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
def _is_valid_header_name(name: bytes) -> bool:
    return bool(name) and all(ch in _ALLOWED_TCHAR for ch in name)


def _validate_no_ctl(value: bytes) -> bool:
    # 允许 HTAB(0x09) 和 VCHAR/obs-text(0x20-0xFF)，拒绝 CR/LF/NUL 等控制字符
    for b in value:
        if b == 0x09:
            continue
        if 0x20 <= b <= 0xFF:
            continue
        return False
    return True

class PendingType(Enum):
    PendingRequestLine=0
    PendingHeader = 1
    PendingBody = 2
    Done = 3
#目前只支持这两种
class Method(Enum):
    UNKNOWN = 9999
    GET = 1
    HEAD = 2
class HttpVersion(Enum):
    Error = "Error"
    HTTP10 = "HTTP/1.0"
    HTTP11 = "HTTP/1.1"

def parse_method_by_name(name: str) -> Optional[Method]:
    try:
        return Method[name]  # 按成员名匹配，严格区分大小写
    except KeyError:
        return Method.UNKNOWN
def parse_http_version_by_name(name: str) -> Optional[HttpVersion]:
    try:
        matcher = {
            "HTTP/1.0": HttpVersion.HTTP10,
            "HTTP/1.1": HttpVersion.HTTP11,
        }
        return matcher[name]  # 按成员名匹配，严格区分大小写
    except KeyError:
        return HttpVersion.Error


class HttpRequestData:
    message: str=""
    method: Method=Method.UNKNOWN
    url: str=""
    http_version: HttpVersion=HttpVersion.Error
    headers: dict[bytes, list[bytes]]={}
    parsed_headers:ParsedHeaders|None
    host: str=""
    port: int=-1
    bodySetting: BodySetting = BodySetting()
    def __init__(self):
        self.message=""
        self.method=Method.UNKNOWN
        self.url=""
        self.http_version=HttpVersion.Error
        self.headers={}
        self.parsed_headers=None
        self.host=""
        self.port=-1
        self.bodySetting= BodySetting()

class ErrorReason(Enum):
    UNKNOWN = 0
    OVERFLOW_MAX_HEADER = 1
    HEADER_FORMAT_ERROR = 2
    BODY_FORMAT_ERROR = 3
    REQUEST_LINE_FORMAT_ERROR = 4
    METHOD_NOT_IMPLEMENTED = 5
    HTTP_VERSION_NOT_SUPPORTED = 6
class HttpStreamResolver:
    pending_type:PendingType
    buffer:str
    data:HttpRequestData
    MAX_HEADER_BYTES = 16 * 1024  # 整个头部最大 16KB
    MAX_HEADER_COUNT = 100  # 最大字段数
    callback:Callable[[bool,Optional[HttpRequestData],Optional[ErrorReason]],None]
    header_resolver:HeaderResolver
    def __init__(self,callback: Callable[[bool,Optional[HttpRequestData],Optional[ErrorReason]],None]):
        self.callback=callback
        self.buffer = ""
        self.pending_type = PendingType.PendingRequestLine
        self.header_resolver = HeaderResolver()
        self.data = HttpRequestData()
    def finalize(self,success=True,error_reason:ErrorReason=ErrorReason.UNKNOWN):
        self.callback(success,self.data if success else None,error_reason)
        self.data = HttpRequestData()
        self.pending_type = PendingType.PendingRequestLine
    def feed(self,s:str):
        self.buffer+=s
        if(self.pending_type == PendingType.PendingRequestLine or self.pending_type == PendingType.PendingHeader) and len(self.buffer)>self.MAX_HEADER_BYTES:
            #头部时超出最大长度
            self.finalize(False,ErrorReason.OVERFLOW_MAX_HEADER)
        if self.pending_type == PendingType.PendingRequestLine:
            finds = self.buffer.find("\r\n")
            if finds>=0:
                self.pending_type=PendingType.PendingHeader
                request_line = self.buffer[:finds]
                self.buffer = self.buffer[finds+2:]#去掉\r\n
                if not self.try_resolve_request(request_line):
                    if self.data.method == Method.UNKNOWN:
                        self.finalize(False,ErrorReason.METHOD_NOT_IMPLEMENTED)
                    elif self.data.http_version == HttpVersion.Error:
                        self.finalize(False,ErrorReason.HTTP_VERSION_NOT_SUPPORTED)
                    else:
                        self.finalize(False,ErrorReason.REQUEST_LINE_FORMAT_ERROR)
                    return
                else:
                    #如果还有接下来的就直接处理Header
                    self.feed("")
            else:
                #没有收到足够消息
                return
        elif self.pending_type == PendingType.PendingHeader:
            allheaders = self.buffer.split("\r\n")
            if len(allheaders)>1:
                complete_index,valid = self.try_resolve_header(allheaders)
                if not valid:
                    #头部解析失败，或者异常
                    self.finalize(False,ErrorReason.HEADER_FORMAT_ERROR)
                else:
                    if complete_index>=0:
                        parse_result = self.header_resolver.resolve_bytes_map(self.data.headers,self.data.http_version.value)
                        if not parse_result.ok:
                            self.finalize(False,ErrorReason.HEADER_FORMAT_ERROR)
                            return
                        self.data.parsed_headers = parse_result.parsed
                        self.buffer = "\r\n".join(allheaders[complete_index:])
                        self.pending_type=PendingType.PendingBody
                        self.data.bodySetting.init(self.data.parsed_headers)
                        #继续处理body
                        self.feed("")
                    else:
                        #try resolve header不处理最后一行
                        self.buffer = allheaders[-1]
            else:
                #没有收到足够消息
                return
        elif self.pending_type == PendingType.PendingBody:
            try:
                #输出是否完成和剩余buffer
                finished, buffer2 = self.data.bodySetting.feed(self.buffer)
                self.buffer = buffer2
                if finished:
                    self.finalize(True)
                    self.feed("")#继续处理下一个请求
                else:
                    return#没有足够消息
            except Exception as e:
                print(e)
                self.finalize(False,ErrorReason.BODY_FORMAT_ERROR)

    def try_resolve_request(self, req: str):
        line = req.split(" ")
        if len(line) != 3:
            return False
        self.data.method = parse_method_by_name(line[0])
        self.data.url = line[1]
        self.data.http_version = parse_http_version_by_name(line[2])
        if self.data.method == Method.UNKNOWN or self.data.http_version == HttpVersion.Error:
            return False
        return True

    def try_resolve_header(self,lines:list[str]) -> tuple[int, bool]:
        ret_complete=-1
        try:
            #永远不处理最后一行，因为最后一行的数据可能没有输入完，得等到输入\r\n才算做一行
            for index,line in enumerate(lines[:-1]):
                if len(line)==0:#因为是逐行读取的，所以这里一定是\r\n\r\n才会出现0的行，说明header结束了
                    ret_complete=index+1
                    break
                #不支持obs-folding
                if line.startswith((" ", "\t")):
                    return ret_complete, False
                #必须有一个冒号
                if line.find(":")<0:
                    return ret_complete, False
                keystr, valuestr = line.split(":", 1)
                # header 名按 RFC 推荐大小写不敏感，统一小写 key
                name = keystr.encode("ascii").lower()
                value = valuestr.encode("latin-1")
                #检查是否合法
                if not _is_valid_header_name(name):
                    return ret_complete, False
                if not _validate_no_ctl(value):
                    return ret_complete, False
                if self.data.headers.get(name) is None:
                    self.data.headers[name] = []
                self.data.headers[name].append(value.strip(b" \t"))

        except Exception as e:
            print("Error resolving")
            print(e)
            return ret_complete,False
        return ret_complete,True
