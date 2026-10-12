# -*- coding: utf-8 -*-
"""验证真机要发布的那份注入脚本：
   1) 滚动条实际宽度是否 = 3px
   2) 网页里按 Esc 是否真的回传了退出消息
直接 import float_browser_native 里的 INJECT_JS / EXIT_MSG，验证的就是发布代码本身。
"""
import os
import time

import clr

from System.Threading import Thread, ThreadStart, ApartmentState

import float_browser_native as fb

LIB = r"C:\Users\admin\.workbuddy\binaries\python\envs\default\Lib\site-packages\webview\lib"

LONG_HTML = ("<!doctype html><html><head><meta charset='utf-8'></head><body>"
             "<div style='height:6000px'>长页面，用于逼出纵向滚动条</div></body></html>")

PROBE_JS = """
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var de=document.documentElement;
      window.chrome.webview.postMessage('MEASURE|'+(window.innerWidth-de.clientWidth));
    }catch(e){ window.chrome.webview.postMessage('MEASURE|ERR '+e); }
    try{
      window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    }catch(e){ window.chrome.webview.postMessage('DISPATCH|ERR '+e); }
  }, 900);
});
"""


def run():
    try:
        clr.AddReference(os.path.join(LIB, "Microsoft.Web.WebView2.Core"))
        clr.AddReference(os.path.join(LIB, "Microsoft.Web.WebView2.WinForms"))
        clr.AddReference("System.Drawing")
        clr.AddReference("System.Windows.Forms")

        for p in (LIB, os.path.join(LIB, "runtimes", "win-x64", "native")):
            if os.path.isdir(p):
                os.environ["Path"] = p + os.pathsep + os.environ.get("Path", "")

        from System.Drawing import Size
        from System.Windows.Forms import (Application, Form, FormBorderStyle,
                                          Padding, DockStyle)
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

        form = Form()
        form.FormBorderStyle = getattr(FormBorderStyle, "None")
        form.Size = Size(700, 500)

        wv = WebView2()
        wv.Margin = Padding(0)
        wv.Dock = DockStyle.Fill
        props = CoreWebView2CreationProperties()
        props.UserDataFolder = fb._user_data_folder()
        wv.CreationProperties = props
        form.Controls.Add(wv)

        msgs = []

        def on_msg(sender, e):
            try:
                m = e.TryGetWebMessageAsString()
            except Exception as ex:
                m = "READFAIL:%r" % ex
            msgs.append(m)
            print("PAGE ->", m, flush=True)

        wv.WebMessageReceived += on_msg

        def on_ready(sender, e):
            print("init success =", e.IsSuccess, flush=True)
            if not e.IsSuccess:
                return
            wv.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(fb.INJECT_JS)
            wv.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(PROBE_JS)
            wv.NavigateToString(LONG_HTML)
            print("navigated; EXIT_MSG = %r" % fb.EXIT_MSG, flush=True)

        wv.CoreWebView2InitializationCompleted += on_ready
        wv.EnsureCoreWebView2Async(None)

        form.Show()
        t0 = time.time()
        while time.time() - t0 < 22:
            Application.DoEvents()
            time.sleep(0.1)
            got_measure = any(m.startswith("MEASURE|") for m in msgs)
            got_exit = fb.EXIT_MSG in msgs
            if got_measure and got_exit and time.time() - t0 > 5:
                break
        form.Close()

        measure = [m for m in msgs if m.startswith("MEASURE|")]
        print()
        print("=== 结论 ===")
        print("滚动条宽度实测 :", measure)
        print("Esc 回传消息   :", "收到 %r" % fb.EXIT_MSG if fb.EXIT_MSG in msgs else "未收到")
        print("全部消息      :", msgs)
    except Exception:
        import traceback
        print("PROBE FAILED:\n" + traceback.format_exc(), flush=True)


t = Thread(ThreadStart(run))
t.SetApartmentState(ApartmentState.STA)
t.Start()
t.Join()
