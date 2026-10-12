# -*- coding: utf-8 -*-
"""列出当前所有与 FloatBrowser 相关的卸载登记项（含新旧两种 AppId 写法）。"""
import winreg

GUID = '2962B13C-41DE-5CAF-A521-B9BEED29FC84'
NAMES = ['%s_is1' % GUID, '{%s}_is1' % GUID]          # 无花括号 / 带花括号
BASE = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
ROOTS = [('HKCU', winreg.HKEY_CURRENT_USER),
         ('HKLM', winreg.HKEY_LOCAL_MACHINE)]

print('=== FloatBrowser 相关卸载登记 ===')
any_found = False
for rname, root in ROOTS:
    for view_flag, view in ((winreg.KEY_WOW64_64KEY, '64'),
                            (winreg.KEY_WOW64_32KEY, '32')):
        for name in NAMES:
            try:
                k = winreg.OpenKey(root, BASE + '\\' + name, 0,
                                   winreg.KEY_READ | view_flag)
            except OSError:
                continue
            any_found = True
            print('[%s / %s位] %s' % (rname, view, name))
            for v in ('DisplayName', 'DisplayVersion', 'InstallLocation',
                      'DisplayIcon', 'UninstallString', 'Publisher'):
                try:
                    print('   %-16s = %s' % (v, winreg.QueryValueEx(k, v)[0]))
                except OSError:
                    print('   %-16s = (none)' % v)
            winreg.CloseKey(k)
if not any_found:
    print('  (无)')

# 顺带列出所有 DisplayName 含「浮窗」的项，防止漏网
print()
print('=== 扫描所有 DisplayName 含「浮窗」的卸载项 ===')
seen = 0
for rname, root in ROOTS:
    for view_flag, view in ((winreg.KEY_WOW64_64KEY, '64'),
                            (winreg.KEY_WOW64_32KEY, '32')):
        try:
            base = winreg.OpenKey(root, BASE, 0,
                                  winreg.KEY_READ | view_flag)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            try:
                k = winreg.OpenKey(base, sub, 0,
                                   winreg.KEY_READ | view_flag)
                dn = winreg.QueryValueEx(k, 'DisplayName')[0]
                il = winreg.QueryValueEx(k, 'InstallLocation')[0]
                winreg.CloseKey(k)
            except OSError:
                continue
            if '浮窗' in str(dn) or 'FloatBrowser' in str(dn):
                seen += 1
                print('  [%s/%s位] %s' % (rname, view, sub))
                print('      DisplayName = %s' % dn)
                print('      Location    = %s' % il)
print('  共 %d 条' % seen)
