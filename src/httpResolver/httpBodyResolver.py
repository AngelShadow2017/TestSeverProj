from enum import Enum

from src.httpResolver.httpHeaderResolver import ParsedHeaders, TransferCoding
from src.httpResolver.normalize_charset import normalize_charset


class BodyMode(Enum):
    NO_BODY = 0
    CONTENT_LENGTH = 1
    CHUNK = 2


class BodySetting:
    has_body:bool=False
    inited:bool=False
    #如果是chunk模式 < 0代表读取下一个chunk，如果读到是0则等待\r\n退出，如果不是chunk模式就是总的
    remaining_bytes:int=-1
    body_mode:BodyMode=BodyMode.NO_BODY
    parsed_charset:str="utf-8"
    body:bytes=b""
    def __init__(self):
        self.has_body=False
        self.inited=False
        self.remaining_bytes=-1
        self.body_mode:BodyMode=BodyMode.NO_BODY
        self.parsed_charset:str="utf-8"
        self.body:bytes=b""
    def init(self,parsed_headers: ParsedHeaders) -> bool:
        self.has_body=False
        self.inited=True
        self.body=b""
        self.parsed_charset=normalize_charset(parsed_headers.content_type_params.get("charset") or self.parsed_charset)
        if parsed_headers.transfer_codings is not None and len(parsed_headers.transfer_codings)>0 and parsed_headers.content_length is not None:
            #错误
            return False
        if len(parsed_headers.transfer_codings)>0 and TransferCoding.CHUNKED in parsed_headers.transfer_codings:
            self.body_mode = BodyMode.CHUNK
            self.remaining_bytes=-1
        elif parsed_headers.content_length is not None and parsed_headers.content_length > 0:
            self.remaining_bytes = parsed_headers.content_length
            self.body_mode = BodyMode.CONTENT_LENGTH
        else:
            self.body_mode = BodyMode.NO_BODY
        return True
    def feed(self,buffer:str) -> tuple[bool,str]:
        if not self.inited:
            raise RuntimeError("Body mode is not initialized")
        if self.body_mode == BodyMode.NO_BODY:
            return True,buffer
        elif self.body_mode == BodyMode.CONTENT_LENGTH:
            buffer_bytes = buffer.encode(self.parsed_charset)
            if len(buffer_bytes)>=self.remaining_bytes:
                #剩余字节数足够了
                remaining_bytes=self.remaining_bytes
                self.body+=buffer_bytes[:remaining_bytes]
                self.remaining_bytes=0
                self.has_body=True
                return True,buffer_bytes[remaining_bytes:].decode(self.parsed_charset)
            else:
                self.body+=buffer_bytes
                self.remaining_bytes-=len(buffer_bytes)
                return False,""
        elif self.body_mode==BodyMode.CHUNK:
            lines = buffer.split("\r\n")
            if len(lines)<2:
                return False, buffer
            last_index=0
            for index,line in enumerate(lines[:-1]):
                last_index=index
                if self.remaining_bytes < 0:
                    #需要读取新的chunk size了
                    try:
                        self.remaining_bytes=int(line,16)
                    except Exception as e:
                        print(e)
                        raise RuntimeError("Error parsing chunk size,")
                else:
                    if self.remaining_bytes==0:
                        if len(line)!=0:
                            raise RuntimeError("Expected empty line after chunk body, got: "+line)
                        #完成出口
                        self.has_body=True
                        return True,"\r\n".join(lines[index+1:])
                    #正在读取chunk body
                    line_bytes = line.encode(self.parsed_charset)+b"\r\n"#目前是数据段
                    if len(line_bytes)>=self.remaining_bytes:
                        self.body+=line_bytes[:self.remaining_bytes]
                        #如果解析完应该是正好解析完，最后留下\r\n的
                        if line_bytes[self.remaining_bytes:]!= b"\r\n":
                            raise RuntimeError("Error parsing chunk size,")
                        self.remaining_bytes=-1
                    else:
                        self.body+=line_bytes
                        self.remaining_bytes-=len(line_bytes)
            return False,"\r\n".join(lines[last_index+1:])
        else:
            return True,buffer