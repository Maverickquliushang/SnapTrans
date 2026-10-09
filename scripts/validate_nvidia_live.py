import asyncio
import json
from pathlib import Path
import sys
import time
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from snaptrans.providers.nvidia import NvidiaProvider
from snaptrans.providers.nvidia_vl import NvidiaVisionProvider
from snaptrans.providers.model_cards import VISION_MODEL
from snaptrans.core.models import ProviderSettings, TranslationRequest, CaptureFrame, AppError

async def main():
    key=sys.stdin.readline().strip()
    async def run(model, vision):
        provider=NvidiaVisionProvider() if vision else NvidiaProvider()
        started=time.monotonic(); phases=[]
        provider.progress=lambda request_id,phase: phases.append(phase) if phase not in phases else None
        try:
            if vision:
                image=Image.new('RGB',(1100,150),'white')
                draw=ImageDraw.Draw(image)
                draw.text((15,20),'The model achieved 95.2% accuracy.',fill='black',font_size=35)
                draw.text((15,75),'Preserve visual evidence across agents.',fill='black',font_size=35)
                frame=CaptureFrame('test','public',(0,0,1100,150),(0,0,1100,150),(0,0,1100,150),1100,150,image.tobytes())
                result=await provider.recognize(frame,dict(provider='nvidia_vl',model=model,max_tokens=4096,total_timeout_seconds=90),key)
                text=result.raw_text
            else:
                settings=ProviderSettings(provider='nvidia',base_url='https://integrate.api.nvidia.com/v1',model=model,
                    max_tokens=4096,model_defaults=False,total_timeout_seconds=90)
                result=await provider.translate(TranslationRequest('test','Translate this sentence: Hello world.',settings),key)
                text=result.text
            report=dict(model=model,vision=vision,ok=True,text=text[:700])
        except AppError as error:
            report=dict(model=model,vision=vision,ok=False,code=error.code,message=error.user_message)
        finally:
            await provider.aclose()
        report.update(seconds=round(time.monotonic()-started,2),phases=phases)
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return report
    result=await asyncio.gather(run('deepseek-ai/deepseek-v4.1-flash',False),run(VISION_MODEL,True))
    (ROOT/'.tmp/v160-adapter-real.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())
