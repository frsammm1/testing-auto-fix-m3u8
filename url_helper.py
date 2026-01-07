import re
import aiohttp
import logging
import m3u8
import json
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

async def get_redirect_url(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
    except:
        return url

async def process_url(url: str, quality: str = None) -> tuple[str, dict]:
    """
    Process URL to extract the actual downloadable link (m3u8/mp4)
    and return specific yt-dlp options if needed.
    Returns: (processed_url, extra_headers/options)
    """
    options = {}

    # 1. VisionIAS
    if "visionias" in url:
        try:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
                'Referer': 'http://www.visionias.in/'
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    text = await resp.text()
                    match = re.search(r"(https://.*?playlist.m3u8.*?)\"", text)
                    if match:
                        return match.group(1), {}
        except Exception as e:
            logger.error(f"VisionIAS extraction failed: {e}")

    # 2. Classplus
    if any(x in url for x in ['videos.classplusapp', 'tencdn.classplusapp', 'webvideos.classplusapp', 'media-cdn-alisg.classplusapp', 'media-cdn-a.classplusapp', 'media-cdn.classplusapp']):
        try:
            # If it's a direct DRM/Media link, use the API from reference
            if 'media-cdn.classplusapp.com/drm/' in url:
                # Reference uses dragoapi
                return f"https://dragoapi.vercel.app/video/{url}", {}

            # Signed URL generation
            api_url = f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}'
            headers = {'x-access-token': 'eyJjb3Vyc2VJZCI6IjQ1NjY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo0ODA2MTksImNhdGVnb3J5SWQiOm51bGx9r'}

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('url', url), {}
        except Exception as e:
            logger.error(f"Classplus extraction failed: {e}")

    # 3. Utkarsh App
    if "apps-s3-jw-prod.utkarshapp.com" in url:
        try:
            if 'enc_plain_mp4' in url:
                # Replace with resolution if possible, else return as is (downloader handles quality)
                pass
            elif '.m3u8' in url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        content = await resp.text()
                        m3u8_obj = m3u8.loads(content)
                        if m3u8_obj.playlists:
                            try:
                                uri = m3u8_obj.playlists[1].uri
                                q = uri.split("/")[0]
                                x = url.split("/")[5]
                                # This reference logic is bit obscure, we'll stick to original URL if unsure
                                pass
                            except:
                                pass
        except Exception as e:
            logger.error(f"Utkarsh extraction failed: {e}")

    # 4. PW.live (Physics Wallah)
    if 'sec-prod-mediacdn.pw.live' in url:
         pass # MPD handling is excluded as per user request

    # 5. Brightcove
    if "edge.api.brightcove.com" in url:
        bcov_auth = 'bcov_auth=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJpYXQiOjE3MjQyMzg3OTEsImNvbiI6eyJpc0FkbWluIjpmYWxzZSwiYXVzZXIiOiJVMFZ6TkdGU2NuQlZjR3h5TkZwV09FYzBURGxOZHowOSIsImlkIjoiZEUxbmNuZFBNblJqVEROVmFWTlFWbXhRTkhoS2R6MDkiLCJmaXJzdF9uYW1lIjoiYVcxV05ITjVSemR6Vm10ak1WUlBSRkF5ZVNzM1VUMDkiLCJlbWFpbCI6Ik5Ga3hNVWhxUXpRNFJ6VlhiR0ppWTJoUk0wMVdNR0pVTlU5clJXSkRWbXRMTTBSU2FHRnhURTFTUlQwPSIsInBob25lIjoiVUhVMFZrOWFTbmQ1ZVcwd1pqUTViRzVSYVc5aGR6MDkiLCJhdmF0YXIiOiJLM1ZzY1M4elMwcDBRbmxrYms4M1JEbHZla05pVVQwOSIsInJlZmVycmFsX2NvZGUiOiJOalZFYzBkM1IyNTBSM3B3VUZWbVRtbHFRVXAwVVQwOSIsImRldmljZV90eXBlIjoiYW5kcm9pZCIsImRldmljZV92ZXJzaW9uIjoiUShBbmRyb2lkIDEwLjApIiwiZGV2aWNlX21vZGVsIjoiU2Ftc3VuZyBTTS1TOTE4QiIsInJlbW90ZV9hZGRyIjoiNTQuMjI2LjI1NS4xNjMsIDU0LjIyNi4yNTUuMTYzIn19.snDdd-PbaoC42OUhn5SJaEGxq0VzfdzO49WTmYgTx8ra_Lz66GySZykpd2SxIZCnrKR6-R10F5sUSrKATv1CDk9ruj_ltCjEkcRq8mAqAytDcEBp72-W0Z7DtGi8LdnY7Vd9Kpaf499P-y3-godolS_7ixClcYOnWxe2nSVD5C9c5HkyisrHTvf6NFAuQC_FD3TzByldbPVKK0ag1UnHRavX8MtttjshnRhv5gJs5DQWj4Ir_dkMcJ4JaVZO3z8j0OxVLjnmuaRBujT-1pavsr1CCzjTbAcBvdjUfvzEhObWfA1-Vl5Y4bUgRHhl1U-0hne4-5fF0aouyu71Y6W0eg'
        if "bcov_auth" not in url:
            url = url.split("?")[0] + "?" + bcov_auth if "?" not in url else url + "&" + bcov_auth
        return url, {}

    # 6. Workers/Madxapi
    if 'workers.dev' in url or 'psitoffers.store' in url or '/master.m3u8' in url:
        if 'cloudfront.net/' in url and 'workers.dev' in url:
            try:
                vid_id = url.split("cloudfront.net/")[1].split("/")[0]
                return f"https://madxapi-d0cbf6ac738c.herokuapp.com/{vid_id}/master.m3u8", {}
            except:
                pass

    # 7. Appx (PDF/Zip/Video)
    if "appx" in url:
        if "pdf" in url:
             return f"https://dragoapi.vercel.app/pdf/{url}", {'type': 'pdf'}
        if ".zip" in url:
             return f"https://video.pablocoder.eu.org/appx-zip?url={url}", {'type': 'zip'}

    # 8. Webvideos (Classplus variation)
    if "webvideos.classplusapp." in url:
        options['http_headers'] = {
            "referer": "https://web.classplusapp.com/",
            "x-cdn-tag": "empty"
        }

    return url, options

def is_youtube_url(url: str) -> bool:
    return any(x in url for x in ['youtube.com', 'youtu.be'])

def is_mpd_url(url: str) -> bool:
    return '.mpd' in url
