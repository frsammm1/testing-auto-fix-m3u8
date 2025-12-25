import aiohttp
import logging
from typing import Optional, Dict, List
from config import COURSES_API, CLASSES_API
from utils import clean_title

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_all_batches(self) -> List[Dict]:
        """Get all available batches"""
        try:
            session = await self.get_session()
            async with session.get(COURSES_API) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    batches = data.get("data", [])
                    
                    result = []
                    for batch in batches:
                        batch_id = batch.get("id") or batch.get("_id")
                        if batch_id:
                            result.append({
                                'id': batch_id,
                                'title': clean_title(batch.get('title', 'Untitled'))
                            })
                    
                    return result
        except Exception as e:
            logger.error(f"Error fetching batches: {e}")
        return []
    
    async def get_batch_content(self, batch_id: str) -> Optional[str]:
        """Get batch content in TXT format"""
        try:
            session = await self.get_session()
            async with session.get(CLASSES_API.format(batch_id)) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                sections = data.get("data", {}).get("classes", [])
                batch_name = clean_title(
                    data.get("data", {}).get("course", {}).get("title", "Batch")
                )
                
                # Build content string
                content = ""
                
                for sec in sections:
                    topic = clean_title(sec.get("topicName", "OTHER")).upper()
                    
                    for cls in sec.get("classes", []):
                        ctitle = clean_title(cls.get("title", "Untitled"))
                        
                        # Video
                        vlink = cls.get("class_link")
                        vids = cls.get("mp4Recordings", [])
                        if vids:
                            sv = sorted(
                                vids, 
                                key=lambda x: int(x['quality'].replace('p','')), 
                                reverse=True
                            )
                            vlink = sv[0]['url']
                        
                        if vlink:
                            content += f"[{topic}] {ctitle}: {vlink}\n"
                        
                        # PDFs
                        for p in cls.get("classPdf", []):
                            p_name = clean_title(p.get('name', 'PDF'))
                            content += f"[{topic}] {p_name}: {p.get('url')}\n"
                        
                        # Tests / Images
                        for t in cls.get("classTest", []):
                            t_name = clean_title(t.get('name', 'Test'))
                            content += f"[{topic}] {t_name}: {t.get('url')}\n"
                        
                        # Banner
                        if cls.get("banner"):
                            content += f"[{topic}] BANNER: {cls.get('banner')}\n"
                
                return content, batch_name
                
        except Exception as e:
            logger.error(f"Error fetching batch content: {e}")
        return None, None

# Global API client
api_client = APIClient()
