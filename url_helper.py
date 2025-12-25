import os
import re
import m3u8
import logging
import aiohttp
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

async def preprocess_url(url: str, headers: dict = None) -> str:
    """
    Preprocess URL to handle specific domains and extraction logic.
    Returns the direct downloadable URL or the original URL if no processing is needed.
    """
    try:
        # Vision IAS
        if "visionias" in url:
            async with aiohttp.ClientSession() as session:
                h = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36'
                }
                async with session.get(url, headers=h) as resp:
                    text = await resp.text()
                    match = re.search(r"(https://.*?playlist.m3u8.*?)\"", text)
                    if match:
                        return match.group(1)

        # Alpha CBSE
        if 'd1d34p8vz63oiq' in url:
            vid_id = url.split("/")[-2]
            return f"https://dl.alphacbse.site/download/{vid_id}/master.m3u8"

        # Classplus (DRM / various domains)
        if 'media-cdn.classplusapp.com/drm/' in url:
             return f"https://dragoapi.vercel.app/video/{url}"

        if any(x in url for x in ['videos.classplusapp', 'tencdn.classplusapp', 'webvideos.classplusapp.com', 'media-cdn-alisg.classplusapp.com', 'media-cdn-a.classplusapp', 'media-cdn.classplusapp', 'alisg-cdn-a.classplusapp']):
            try:
                # Use env var for token, default to placeholder if not set to avoid committing secrets
                token = os.environ.get('CLASSPLUS_TOKEN', 'REPLACE_WITH_YOUR_TOKEN')
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}',
                        headers={'x-access-token': token}
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data['url']
            except Exception as e:
                logger.error(f"Classplus API error: {e}")

        # Utkarsh App
        if "apps-s3-jw-prod.utkarshapp.com" in url:
            if 'enc_plain_mp4' in url:
                pass
            elif 'Key-Pair-Id' in url:
                return url # Return original URL instead of None to prevent crash
            elif '.m3u8' in url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as r:
                            text = await r.text()
                            m3u8_obj = m3u8.loads(text)
                            if m3u8_obj.playlists and len(m3u8_obj.playlists) > 1:
                                q = m3u8_obj.playlists[1].uri.split("/")[0]
                                parts = url.split("/")
                                if len(parts) > 5:
                                    x = parts[5]
                                    x_replaced = url.replace(x, "")
                                    return m3u8_obj.playlists[1].uri.replace(q+"/", x_replaced)
                except Exception as e:
                    logger.error(f"Utkarsh m3u8 parsing error: {e}")

        # Adda247 / AmazonAWS
        if 'amazonaws.com' in url:
            # Requires token and quality, which we might not have in this context.
            # Assuming the URL might already be processed or we skip this specific enhancement if args missing.
            pass

        # Appx / Zip / PDF special handling (DragoAPI)
        if "appx" in url and "pdf" in url:
            return f"https://dragoapi.vercel.app/pdf/{url}"

        if ".zip" in url:
             return f"https://video.pablocoder.eu.org/appx-zip?url={url}"

        # PW (Physics Wallah)
        if 'sec-prod-mediacdn.pw.live' in url:
            try:
                vid_id = url.split("sec-prod-mediacdn.pw.live/")[1].split("/")[0]
                # Note: Token is required for this API in the reference code.
                # If we don't have the token, this might fail.
                # The reference code gets token from user input.
                # We'll return original URL if we can't process it.
                return url
            except IndexError:
                pass

        if '/master.mpd' in url and 'pw.live' in url:
             # PW links API
             try:
                 vid_id = url.split("/")[-2]
                 # Defaulting quality to 480 or similar if needed, but the API might need it.
                 return f"https://pw-links-api.onrender.com/process?v=https://sec1.pw.live/{vid_id}/master.mpd&quality=480"
             except:
                 pass

        # Bitgravity
        if 'bitgravity.com' in url:
            try:
                parts = url.split('/')
                if len(parts) > 6:
                    part3 = parts[3]
                    part4 = parts[4]
                    part5 = parts[5]
                    part6 = parts[6]
                    return f"https://kgs-v2.akamaized.net/{part3}/{part4}/{part5}/{part6}"
            except IndexError:
                pass

        # Workers.dev / Psitoffers
        if 'workers.dev' in url:
            try:
                 vid_id = url.split("cloudfront.net/")[1].split("/")[0]
                 return f"https://madxapi-d0cbf6ac738c.herokuapp.com/{vid_id}/master.m3u8" # Token needed?
            except:
                pass

        if 'psitoffers.store' in url:
            try:
                vid_id = url.split("vid=")[1].split("&")[0]
                return f"https://madxapi-d0cbf6ac738c.herokuapp.com/{vid_id}/master.m3u8"
            except:
                pass

        # Brightcove
        if "edge.api.brightcove.com" in url:
            # Using environment variable for auth token to avoid hardcoding PII/Secrets
            # Fallback to a placeholder if not set, but do not commit the PII-laden token.
            bcov_auth_token = os.environ.get('BCOV_AUTH_TOKEN', 'bcov_auth=REPLACE_WITH_YOUR_TOKEN_IF_NEEDED')
            return url.split("bcov_auth")[0] + bcov_auth_token

        # Khan Global Studies PDF
        if '/do' in url and '.pdf' in url:
             pdf_id = url.split("/")[-1].split(".pdf")[0]
             return f"https://kgs-v2.akamaized.net/kgs/do/pdfs/{pdf_id}.pdf"

        # Youtube Embed
        if '?list' in url and '/embed/' in url:
             video_id = url.split("/embed/")[1].split("?")[0]
             return f"https://www.youtube.com/embed/{video_id}"

        return url

    except Exception as e:
        logger.error(f"Error preprocessing URL {url}: {e}")
        return url

def get_ytdlp_args(url: str, output_path: str, cookies_path: str = "youtube_cookies.txt") -> dict:
    """
    Get aggressive yt-dlp arguments based on the URL type.
    """

    # Base arguments with aggressive settings from reference repo
    args = {
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'concurrent_fragment_downloads': 16, # Increased workers
        'retries': 25,     # Aggressive retries
        'fragment_retries': 25,
        'buffersize': 1024 * 1024,
        'http_chunk_size': 10485760,
        'hls_prefer_native': True,
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-x', '16', '-j', '32', '-k', '1M'], # Aggressive aria2c
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
    }

    # Specific format handling
    if "youtu" in url:
        # Reference repo uses specific format string for YouTube
        # f"b[height<={raw_text2}][ext=mp4]/bv[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]"
        # We default to best quality if not specified, or we can use a generic "best"
        args['format'] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        if os.path.exists(cookies_path):
            args['cookiefile'] = cookies_path

    elif "webvideos.classplusapp." in url:
        args['http_headers'] = {
            "referer": "https://web.classplusapp.com/",
            "x-cdn-tag": "empty"
        }

    else:
        args['format'] = "bestvideo+bestaudio/best"

    return args
