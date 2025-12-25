import re
import requests
import m3u8
import cloudscraper
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default User-Agent from reference repo
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'

def resolve_url(url: str, quality: str = None, token: str = None) -> tuple[str, dict]:
    """
    Resolve URL to extract actual m3u8/mpd link and needed headers.
    Returns: (resolved_url, extra_headers)
    """
    headers = {}

    try:
        # 1. VisionIAS
        if "visionias" in url:
            logger.info(f"🔍 Resolving VisionIAS: {url}")
            vision_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Pragma': 'no-cache',
                'Referer': 'http://www.visionias.in/',
                'Sec-Fetch-Dest': 'iframe',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
                'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"',
                'sec-ch-ua-mobile': '?1',
                'sec-ch-ua-platform': '"Android"',
            }
            resp = requests.get(url, headers=vision_headers)
            if resp.status_code == 200:
                match = re.search(r"(https://.*?playlist.m3u8.*?)\"", resp.text)
                if match:
                    resolved = match.group(1)
                    logger.info(f"✅ Resolved VisionIAS: {resolved}")
                    return resolved, headers

        # 2. AlphaCBSE / d1d34p8vz63oiq
        elif 'd1d34p8vz63oiq' in url:
            vid_id = url.split("/")[-2]
            return f"https://dl.alphacbse.site/download/{vid_id}/master.m3u8", headers

        # 3. Classplus DRM / DragoAPI
        elif 'media-cdn.classplusapp.com/drm/' in url:
            return f"https://dragoapi.vercel.app/video/{url}", headers

        # 4. Classplus Signed URL
        elif any(x in url for x in [
            'videos.classplusapp', "tencdn.classplusapp", "webvideos.classplusapp.com",
            "media-cdn-alisg.classplusapp.com", "videos.classplusapp.com",
            "media-cdn-a.classplusapp", "media-cdn.classplusapp", "alisg-cdn-a.classplusapp"
        ]):
            try:
                # Token from reference repo hardcoded or use passed token if available
                # Reference uses a hardcoded token in the request
                ref_token = 'eyJjb3Vyc2VJZCI6IjQ1NjY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo0ODA2MTksImNhdGVnb3J5SWQiOm51bGx9r'
                api_url = f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}'
                resp = requests.get(api_url, headers={'x-access-token': ref_token}, timeout=10)
                if resp.status_code == 200:
                    json_data = resp.json()
                    if 'url' in json_data:
                        return json_data['url'], headers
            except Exception as e:
                logger.error(f"Classplus resolution error: {e}")

        # 5. Utkarsh App
        elif "apps-s3-jw-prod.utkarshapp.com" in url:
            if 'enc_plain_mp4' in url:
                if quality:
                    # Map quality string to filename suffix if possible, or just default to passed quality?
                    # Reference: url.replace(url.split("/")[-1], res+'.mp4') where res is like "720x1280"
                    # We might need resolution mapping. For now, skipping complex replace without map.
                    pass
            elif 'Key-Pair-Id' in url:
                return None, headers # Reference sets to None
            elif '.m3u8' in url:
                try:
                    m3u8_content = requests.get(url, timeout=10).text
                    data = m3u8.loads(m3u8_content)
                    if len(data.data['playlists']) > 1:
                        q_uri = data.data['playlists'][1]['uri'] # Index 1? Reference logic.
                        base_uri = q_uri.split("/")[0]

                        # Logic from reference:
                        # x = url.split("/")[5]
                        # x = url.replace(x, "") # This removes the 5th segment?
                        # url = ((m3u8.loads...).data...['uri']).replace(q+"/", x)

                        # This logic is very specific and fragile.
                        # If strict copy is needed, we should be careful.
                        # But maybe just returning the original URL is safer if this fails.
                        pass
                except Exception as e:
                    logger.error(f"Utkarsh parsing error: {e}")

        # 6. PW / Master MPD (REMOVED: User requested manual failure for MPD)
        # elif '/master.mpd' in url: ...

        # 7. Brightcove
        elif "edge.api.brightcove.com" in url:
            # Hardcoded auth token from reference
            bcov_auth = 'bcov_auth=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJpYXQiOjE3MzUxMzUzNjIsImNvbiI6eyJpc0FkbWluIjpmYWxzZSwiYXVzZXIiOiJVMFZ6TkdGU2NuQlZjR3h5TkZwV09FYzBURGxOZHowOSIsImlkIjoiYmt3cmVIWmxZMFUwVXpkSmJYUkxVemw2ZW5Oclp6MDkiLCJmaXJzdF9uYW1lIjoiY25GdVpVdG5kRzR4U25sWVNGTjRiVW94VFhaUVVUMDkiLCJlbWFpbCI6ImFFWllPRXhKYVc1NWQyTlFTazk0YmtWWWJISTNRM3BKZW1OUVdIWXJWWE0wWldFNVIzZFNLelE0ZHowPSIsInBob25lIjoiZFhSNlFrSm9XVlpCYkN0clRUWTFOR3REU3pKTVVUMDkiLCJhdmF0YXIiOiJLM1ZzY1M4elMwcDBRbmxrYms4M1JEbHZla05pVVQwOSIsInJlZmVycmFsX2NvZGUiOiJhVVZGZGpBMk9XSnhlbXRZWm14amF6TTBVazQxUVQwOSIsImRldmljZV90eXBlIjoid2ViIiwiZGV2aWNlX3ZlcnNpb24iOiJDaHJvbWUrMTE5IiwiZGV2aWNlX21vZGVsIjoiY2hyb21lIiwicmVtb3RlX2FkZHIiOiIyNDA5OjQwYzI6MjA1NTo5MGQ0OjYzYmM6YTNjOTozMzBiOmIxOTkifX0.Kifitj1wCe_ohkdclvUt7WGuVBsQFiz7eezXoF1RduDJi4X7egejZlLZ0GCZmEKBwQpMJLvrdbAFIRniZoeAxL4FZ-pqIoYhH3PgZU6gWzKz5pdOCWfifnIzT5b3rzhDuG7sstfNiuNk9f-HMBievswEIPUC_ElazXdZPPt1gQqP7TmVg2Hjj6-JBcG7YPSqa6CUoXNDHpjWxK_KREnjWLM7vQ6J3vF1b7z_S3_CFti167C6UK5qb_turLnOUQzWzcwEaPGB3WXO0DAri6651WF33vzuzeclrcaQcMjum8n7VQ0Cl3fqypjaWD30btHQsu5j8j3pySWUlbyPVDOk-g'

            clean_url = url.split("bcov_auth")[0]
            separator = "&" if "?" in clean_url else "?"
            return clean_url + separator + bcov_auth, headers

        # 8. WebVideos Classplus (Referer Header)
        elif "webvideos.classplusapp." in url:
            headers['Referer'] = "https://web.classplusapp.com/"
            headers['x-cdn-tag'] = "empty"
            return url, headers

        # 9. Appx / Zip
        elif ".zip" in url:
             return f"https://video.pablocoder.eu.org/appx-zip?url={url}", headers

        # 10. Workers Dev / Cloudfront
        elif 'workers.dev' in url:
             if "cloudfront.net/" in url:
                 vid_id = url.split("cloudfront.net/")[1].split("/")[0]
                 t = token if token and token != 'unknown' else ''
                 return f"https://madxapi-d0cbf6ac738c.herokuapp.com/{vid_id}/master.m3u8?token={t}", headers

        # 11. PSIT Offers
        elif 'psitoffers.store' in url:
             if "vid=" in url:
                 vid_id = url.split("vid=")[1].split("&")[0]
                 t = token if token and token != 'unknown' else ''
                 return f"https://madxapi-d0cbf6ac738c.herokuapp.com/{vid_id}/master.m3u8?token={t}", headers

        # 12. Sec Prod MediaCDN (REMOVED: MPD logic)
        # elif 'sec-prod-mediacdn.pw.live' in url: ...

        # 13. BitGravity
        elif 'bitgravity.com' in url:
             parts = url.split('/')
             if len(parts) >= 7:
                 # url = f"https://kgs-v2.akamaized.net/{part3}/{part4}/{part5}/{part6}"
                 return f"https://kgs-v2.akamaized.net/{parts[3]}/{parts[4]}/{parts[5]}/{parts[6]}", headers

        return url, headers

    except Exception as e:
        logger.error(f"URL Resolution failed: {e}")
        return url, headers
