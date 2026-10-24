
import os, re, requests, subprocess, threading, uuid, json
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
jobs={}
def get_html_file():
    try: return open('index.html','r',encoding='utf-8').read()
    except: return "OK"
HEADERS={
"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
"Referer":"https://www.bigo.tv/",
"Origin":"https://www.bigo.tv",
"Accept":"*/*",
"Accept-Language":"th-TH,th;q=0.9,en;q=0.8",
}
def resolve_any(url):
    url=url.strip()
    if "slink" in url or "onelink" in url:
        try:
            s=requests.Session()
            r=s.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text)
            if m: return m.group(0).replace("\\u002F","/").split('"')[0], f"slink html -> sid len {len(r.text)}\n"
            if "/sid/" in r.url: return r.url, f"slink redirect -> {r.url}\n"
            return r.url, f"slink -> {r.url}\n"
        except Exception as e: return url, f"err {e}\n"
    return url, ""

def deep_extract(sid_url):
    log=""
    full=sid_url
    m_sid=re.search(r"/sid/([^?]+)", full)
    site_full=m_sid.group(1) if m_sid else ""
    site_id=site_full.split("_")[0] if "_" in site_full else site_full
    qs=full.split("?",1)[1] if "?" in full else ""
    params=dict(kv.split("=",1) for kv in qs.split("&") if "=" in kv)
    b=params.get("b",""); h=params.get("h",""); mk=params.get("mk","")
    log+=f"site_id={site_id} full={site_full[:40]}\n b={b} h={h} mk={mk[:15]}...\n"

    # 1. GET full page and save
    try:
        r=requests.get(full, headers=HEADERS, timeout=15)
        log+=f"GET sid page {r.status_code} len {len(r.text)}\n"
        txt=r.text
        # save for debug
        try:
            open(f"/tmp/page_{site_id}.html","w",encoding="utf-8").write(txt[:200000])
        except: pass
        # deep search keywords
        keywords=["flvPullUrl","hlsPullUrl","pullUrl","playUrl","src","flv","m3u8","hls","liveUrl","videoSrc","streamUrl","rtmp"]
        for kw in keywords:
            # find kw near url
            for mm in re.finditer(kw, txt, re.IGNORECASE):
                snippet=txt[max(0,mm.start()-200):mm.start()+500]
                if ".m3u8" in snippet or ".flv" in snippet or "bigo" in snippet.lower():
                    # extract url in snippet
                    um=re.search(r"https?://[^\"\'\s<>]+\.(?:m3u8|flv)[^\"\'\s<>]*", snippet.replace("\\u002F","/"))
                    if um:
                        clean=um.group(0).split('"')[0]
                        log+=f"FOUND by keyword {kw}: {clean[:200]}\n"
                        return clean, log+f"FOUND keyword {kw}\n", "live"
        # generic m3u8/flv search in whole page (unescape)
        txt_u=txt.replace("\\u002F","/").replace("\\/","/").replace("\\","")
        all_m3u8=re.findall(r"https?://[^"]+\.m3u8[^"]*", txt_u)
        all_flv=re.findall(r"https?://[^"]+\.flv[^"]*", txt_u)
        log+=f"generic search: {len(all_m3u8)} m3u8, {len(all_flv)} flv\n"
        for u in (all_m3u8+all_flv)[:3]:
            log+=f"  candidate {u[:200]}\n"
        if all_m3u8:
            return all_m3u8[0].split('"')[0], log+"FOUND generic m3u8\n", "live"
        if all_flv:
            return all_flv[0].split('"')[0], log+"FOUND generic flv\n", "live"

        # search in JSON blobs
        for blob in re.findall(r"<script[^>]*>(.+?)</script>", txt, re.DOTALL)[:20]:
            if "m3u8" in blob or "flv" in blob or "pullUrl" in blob:
                mm=re.search(r"https?://[^\"\'\s<>]+\.(?:m3u8|flv)[^\"\'\s<>]*", blob.replace("\\u002F","/"))
                if mm:
                    clean=mm.group(0).split('"')[0]
                    log+=f"FOUND in script: {clean[:200]}\n"
                    return clean, log+"FOUND script\n", "live"

    except Exception as e:
        log+=f"page err {e}\n"

    # 2. Try Bigo undocumented API with proper headers
    apis=[
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}",
        f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}",
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
        f"https://www.bigo.tv/v1/live/getLiveInfo?siteId={site_id}&b={b}&h={h}",
        f"https://bigo.tv/v1/live/getLiveInfo?siteId={site_id}",
    ]
    for api in apis:
        try:
            hh=dict(HEADERS); hh["X-Requested-With"]="XMLHttpRequest"
            rr=requests.get(api, headers=hh, timeout=10)
            log+=f"API {api[:90]} -> {rr.status_code} len {len(rr.text)} ct {rr.headers.get('content-type','')}\n"
            if ".m3u8" in rr.text or ".flv" in rr.text:
                mm=re.search(r"https?://[^\"\'\s<>]+\.(?:m3u8|flv)[^\"\'\s<>]*", rr.text.replace("\\u002F","/"))
                if mm:
                    clean=mm.group(0).split('"')[0]
                    log+=f"FOUND API {clean[:200]}\n"
                    return clean, log+f"FOUND API {api[:60]}\n", "live"
            # try json
            try:
                j=json.loads(rr.text)
                # recursive find
                stack=[j]
                while stack:
                    cur=stack.pop()
                    if isinstance(cur, dict):
                        for k,v in cur.items():
                            if isinstance(v,str) and (".m3u8" in v or ".flv" in v) and "http" in v:
                                log+=f"FOUND in json field {k}: {v[:200]}\n"
                                return v, log+"FOUND json\n", "live"
                            if isinstance(v,(dict,list)): stack.append(v)
                    elif isinstance(cur,list):
                        for it in cur: stack.append(it)
            except: pass
            log+=f"API body start: {rr.text[:400]}\n"
        except Exception as e:
            log+=f"API err {e}\n"

    # 3. yt-dlp extract with cookies
    try:
        log+="Trying yt-dlp --print-url\n"
        proc=subprocess.Popen(["yt-dlp","--no-warnings","-g",full], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out, _=proc.communicate(timeout=20)
        log+=f"yt-dlp -g: {out[:800]}\n"
        if ".m3u8" in out or ".flv" in out:
            m=re.search(r"https?://[^\s]+\.(?:m3u8|flv)[^\s]*", out)
            if m: return m.group(0), log+"FOUND yt-dlp -g\n", "live"
    except Exception as e:
        log+=f"yt-dlp err {e}\n"

    return None, log, "offline"

@app.route("/")
def home(): return get_html_file()
@app.route("/api/start", methods=["POST"])
def api_start():
    data=request.json; raw=data.get("url","")
    mm=re.search(r"https?://[^\s]+", raw); raw_url=mm.group(0).strip(')"\'\'') if mm else raw.strip()
    resolved, slog = resolve_any(raw_url)
    mm2=re.search(r"/sid/(\d+)", resolved); site_id=mm2.group(1) if mm2 else "unknown"
    job_id=uuid.uuid4().hex[:8]
    RECORD_DIR="/tmp/recordings"; os.makedirs(RECORD_DIR, exist_ok=True)
    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"checking","status_msg":"ขุดลึกหา HLS ตอนไลฟ์สด","log":slog,"time":datetime.now().strftime("%H:%M:%S")}
    def run():
        try:
            hls, plog, state = deep_extract(resolved)
            log=slog+plog
            jobs[job_id]["log"]=log
            if not hls:
                jobs[job_id]["status"]="offline"
                jobs[job_id]["status_msg"]=f"ยังขุดไม่เจอ HLS - ส่ง Log ให้ดู"
                return
            jobs[job_id]["status"]="recording"
            jobs[job_id]["status_msg"]=f"LIVE กำลังอัด! {site_id}"
            cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-15000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            jobs[job_id]["status_msg"]="อัดเสร็จ done" if proc.returncode==0 else "ffmpeg error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e); jobs[job_id]["status"]="error"; jobs[job_id]["status_msg"]=str(e)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"status_msg":"ขุดลึก..."})
@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])
if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
