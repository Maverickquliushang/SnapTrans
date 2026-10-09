"""Compare public synthetic paper text through the two NVIDIA OCR paths."""
import asyncio,json,sys,time,textwrap
from pathlib import Path
from difflib import SequenceMatcher
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from snaptrans.providers.nvidia_ocr import NvidiaOcrProvider
from snaptrans.providers.nvidia_vl import NvidiaVisionProvider
from snaptrans.providers.model_cards import VISION_MODEL
from snaptrans.core.models import CaptureFrame,AppError
TEXT=('Visual language models combine image understanding with language generation. '
      'This experiment measures whether visual evidence is preserved when several agents work together. '
      'The baseline model achieved 95.2% accuracy on 120 examples. We evaluate text recognition and translation separately. '
      'All names, numerical values, punctuation, and paragraph boundaries should remain unchanged during transcription. '
      'These sentences are a public synthetic sample created for software testing; they contain no private document content.')
async def main():
    key=sys.stdin.readline().strip()
    image=Image.new('RGB',(1900,220),'white');draw=ImageDraw.Draw(image)
    for i,line in enumerate(textwrap.wrap(TEXT,150)):
        draw.text((18,18+i*36),line,fill='black',font_size=21)
    folder=ROOT/'.tmp/v160-ocr-comparison';folder.mkdir(exist_ok=True)
    image.save(folder/'public-paper-sample.png')
    frame=CaptureFrame('public','test',(0,0,1900,220),(0,0,1900,220),(0,0,1900,220),1900,220,image.tobytes())
    async def run(kind):
        provider=NvidiaVisionProvider() if kind=='vision' else NvidiaOcrProvider()
        started=time.monotonic()
        try:
            result=await provider.recognize(frame,dict(provider='nvidia_vl' if kind=='vision' else 'nvidia',
                model=VISION_MODEL,max_tokens=4096,total_timeout_seconds=60),key)
            normalized=' '.join(result.raw_text.split())
            report=dict(kind=kind,ok=True,text=result.raw_text,similarity=round(SequenceMatcher(None,TEXT,normalized).ratio(),4))
        except AppError as e:report=dict(kind=kind,ok=False,code=e.code,message=e.user_message)
        finally:await provider.aclose()
        report['seconds']=round(time.monotonic()-started,2)
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return report
    reports=await asyncio.gather(run('dedicated'),run('vision'))
    (folder/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':asyncio.run(main())
