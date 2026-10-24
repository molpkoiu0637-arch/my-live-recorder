
import os, re, requests, subprocess, threading, uuid
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = """<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>BIGO V21 SINGAPORE</title><style>body{background:#0a0a0a;color:#fff;font-family:system-ui;padding:14px}.card{background:#1c1c1e;border-radius:18px;padding:18px;margin:14px 0;border:1px solid #2c2c2e}input{width:100%;padding:18px;border-radius:14px;border:2px solid #ff9500;background:#2c2c2e;color:#fff;font-size:16px;box-sizing:border-box}button{width:100%;padding:18px;border-radius:14px;border:none;font-weight:800;font-size:18px;margin:10px 0}.btn-orange{background:#ff9500;color:#000}.badge{background:#30d158;color:#000;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:800}pre{background:#000;padding:12px;border-radius:10px;white-space:pre-wrap;font-size:12px;max-height:500px;overflow:auto}.small{color:#8e8e93;font-size:13px;line-height:1.5}</style></head><body><h2>BIGO V21 <span class=badge>SINGAPORE - วางแล้วอัดเลย</span></h2><p class=small>เหมือนเว็บอื่นแล้ว: วาง slink / bigo.tv/th/xxx / ชื่อยูส แล้วกดปุ่มเดียวจบ<br>Server อยู่สิงคโปร์ ไม่โดนบล็อกแล้ว</p><div class=card><p style=color:#ff9500;font-weight:bold>วางตรงนี้เลย</p><input id=url placeholder="วางลิงก์ เช่น https://slink.bigovideo.tv/xxxx หรือ https://www.bigo.tv/th/1140986432"><button class=btn-orange onclick=start()>🔴 วางแล้วกดบันทึกเลย</button><div id=status style=color:#30d158;font-weight:bold;margin-top:12px;font-size:14px"></div><div id=list style=margin-top:16px></div></div><div class=card><p class=small>ตัวอย่างที่วางได้:<br>- https://slink.bigovideo.tv/xxxx<br>- https://www.bigo.tv/th/1140986432<br>- ชื่อยูสอย่างเดียวก็ได้</p></div><script>async function start(){let raw=document.getElementById('url').value.trim();if(!raw){alert('วางลิงก์ก่อนครับ');return;}let url=(raw.match(/https?:\/\/[^\s]+/)||[raw])[0];document.getElementById('status').innerHTML='⏳ กำลังแกะลิงก์... '+url.slice(0,80)+'<br>รอ 10-20 วิ...';try{let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});let j=await r.json();if(j.error){document.getElementById('status').innerHTML='❌ '+j.error;return;}document.getElementById('status').innerHTML='✅ OK ID '+j.id+'<br>📍 Resolved: '+j.resolved.slice(0,150)+'<br>🆔 SiteID: '+j.siteid+'<br><br>กำลังอัด ดู Log ข้างล่าง';load();}catch(e){document.getElementById('status').innerHTML='❌ Error: '+e;}}async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{let color=it.status=='done'?'#30d158':(it.status=='error'?'#ff3b30':'#ff9500');h+=`<div class=card style=border-left:5px solid ${color}><b style=color:${color}>${it.status.toUpperCase()}</b> - ${it.time}<br><small>${it.resolved.slice(0,200)}</small><br><small>SiteID: ${it.siteid}</small><pre>${(it.log||'').slice(-5000)}</pre></div>`;});document.getElementById('list').innerHTML=h;}setInterval(load,3000);load();</script></body></html>"""

HEADERS={"User-Agent":"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36","Referer":"https://www.bigo.tv/"}

def resolve_any_url(url):
    log=""
    if re.match(r"^\d+$", url.strip()):
        url=f"https://www.bigo.tv/th/{url.strip()}"
        log+=f"ID -> {url}\n"
    if not url.startswith("http"):
        if re.match(r"^[A-Za-z0-9_\.]+$", url):
            url=f"https://www.bigo.tv/{url}"
            log+=f"username -> {url}\n"
    if "slink" in url or "onelink" in url:
        try:
            s=requests.Session()
            r=s.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            log+=f"slink GET {r.status_code} -> {r.url}\n"
            if "bigo.tv" in r.url and "slink" not in r.url and "onelink" not in r.url:
                return r.url, log
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text)
            if m:
                sid=m.group(0).replace("\u002F","/").split('"')[0]
                return sid, log+f"found sid {sid[:80]}\n"
            return r.url, log
        except Exception as e:
            return url, log+f"err {e}\n"
    if "bigo.tv" in url and "/sid/" not in url:
        try:
            r=requests.get(url, headers=HEADERS, timeout=12)
            log+=f"GET user page {r.status_code}\n"
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text.replace("\u002F","/"))
            if m:
                sid=m.group(0).replace("\u002F","/").split('"')[0]
                return sid, log+f"user page -> sid {sid[:100]}\n"
        except Exception as e:
            log+=f"user page err {e}\n"
    return url, log

def get_hls(sid_url):
    log=""
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET sid {r.status_code} len {len(r.text)}\n"
        txt=r.text.replace("\u002F","/")
        m3us=re.findall(r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*", txt)
        m3us=list(dict.fromkeys(m3us))
        log+=f"found {len(m3us)} m3u8\n"
        for u in m3us[:2]: log+=u[:200]+"\n"
        if m3us:
            return m3us[0].split('"')[0], log
        mm=re.search(r"/sid/(\d+)", sid_url)
        if mm:
            site_id=mm.group(1)
            api=f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}"
            rr=requests.get(api, headers=HEADERS, timeout=10)
            log+=f"API {api} {rr.status_code}\n"
            if ".m3u8" in rr.text:
                m=re.search(r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*", rr.text)
                if m:
                    return m.group(0), log+"FOUND API\n"
    except Exception as e:
        log+=f"err {e}\n"
    return None, log

@app.route("/")
def home(): return HTML_PAGE

@app.route("/api/start", methods=["POST"])
def api_start():
    data=request.json
    raw=data.get("url","")
    mm=re.search(r"https?://[^\s]+", raw)
    raw_url=mm.group(0).strip(')"\''') if mm else raw.strip()
    resolved, slog = resolve_any_url(raw_url)
    mm2=re.search(r"/sid/(\d+)", resolved)
    site_id=mm2.group(1) if mm2 else "unknown"
    if site_id=="unknown":
        mm3=re.search(r"/th/(\d+)", resolved)
        if mm3: site_id=mm3.group(1)
    out=os.path.join(RECORD_DIR, f"{uuid.uuid4().hex[:8]}.mp4")
    job_id=uuid.uuid4().hex[:8]
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"starting","log":slog,"time":datetime.now().strftime("%H:%M:%S"),"file":out}
    def run():
        try:
            jobs[job_id]["status"]="recording"
            log=slog+f"\nResolved: {resolved}\nSiteID: {site_id}\n"
            hls, plog = get_hls(resolved)
            log+=plog
            if hls:
                log+=f"\nFOUND HLS SINGAPORE {hls[:100]}\n"
                jobs[job_id]["log"]=log
                cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
                proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
                proc.wait()
                jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            else:
                log+="\nไม่เจอ HLS - คนนี้อาจไม่ได้ไลฟ์สดอยู่\n"
                jobs[job_id]["log"]=log
                cmd=["yt-dlp","-f","best","-o",out, resolved]
                proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
                proc.wait()
                jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id})

@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])

if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
