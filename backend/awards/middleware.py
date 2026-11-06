"""Keep large certificate/font downloads bounded under ASGI."""

import asyncio
from asgiref.sync import iscoroutinefunction
from django.http import FileResponse
from django.utils.decorators import sync_and_async_middleware


@sync_and_async_middleware
def async_file_streaming(get_response):
    if iscoroutinefunction(get_response):

        async def middleware(request):
            response = await get_response(request)
            if isinstance(response, FileResponse) and not response.is_async:
                source = response.file_to_stream
                if source is not None:

                    async def chunks():
                        try:
                            while True:
                                chunk = await asyncio.to_thread(source.read, 64 * 1024)
                                if not chunk:
                                    break
                                yield chunk
                        finally:
                            source.close()

                    # FileResponse already set Content-Length, MIME and disposition.
                    response.streaming_content = chunks()
            return response

    else:

        def middleware(request):
            return get_response(request)

    return middleware
