#!/usr/bin/env python3
"""List available tools and sources through the official MCP client; no message bodies printed."""
import argparse, asyncio, json
from pathlib import Path
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def inspect_endpoint(url, token):
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token},timeout=30) as http:
        async with streamable_http_client(url,http_client=http) as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                tools=await session.list_tools()
                sources=await session.call_tool('list_sources',{})
                result=sources.model_dump(by_alias=True)
                if result.get('isError'):
                    raise RuntimeError('MCP source query failed; check the key permissions')
                return {'tools':[t.name for t in tools.tools], 'sources':result.get('structuredContent')}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--token-file',type=Path,required=True)
    a=p.parse_args();print(json.dumps(asyncio.run(inspect_endpoint(a.url,a.token_file.read_text().strip())),ensure_ascii=False,indent=2))
