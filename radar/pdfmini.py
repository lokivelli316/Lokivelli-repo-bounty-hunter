from __future__ import annotations
from pathlib import Path

def _esc(s:str)->str:
    return s.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')

def write_text_pdf(path:Path,title:str,lines:list[str]):
    pages=[]; chunk=[]
    for line in [title,""]+lines:
        if len(line)>110:
            while len(line)>110:
                cut=line.rfind(' ',0,110)
                if cut<40: cut=110
                chunk.append(line[:cut]); line=line[cut:].lstrip()
                if len(chunk)>=52: pages.append(chunk); chunk=[]
        chunk.append(line)
        if len(chunk)>=52: pages.append(chunk); chunk=[]
    if chunk or not pages: pages.append(chunk)
    objs=["<< /Type /Catalog /Pages 2 0 R >>"]
    kids=[]; page_obj_ids=[]; content_obj_ids=[]; next_id=4
    for _ in pages:
        page_obj_ids.append(next_id); content_obj_ids.append(next_id+1); kids.append(f"{next_id} 0 R"); next_id+=2
    objs.append(f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page,page_id,content_id in zip(pages,page_obj_ids,content_obj_ids):
        stream=["BT /F1 10 Tf 50 742 Td 12 TL"]
        for i,line in enumerate(page):
            if i: stream.append("T*")
            stream.append(f"({_esc(line)}) Tj")
        stream.append("ET"); data="\n".join(stream)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>")
        objs.append(f"<< /Length {len(data.encode())} >>\nstream\n{data}\nendstream")
    out=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for i,obj in enumerate(objs,1):
        offsets.append(len(out)); out.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref=len(out); out.extend(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(out)
