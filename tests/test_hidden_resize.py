import copy
import importlib.util
from pathlib import Path
import unittest
from contextlib import contextmanager

spec = importlib.util.spec_from_file_location("hidden_resize", Path(__file__).parents[1] / "src/lowlevel_computer_use_mcp/hidden_resize.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Fake:
    def __init__(self):
        self.calls = []; self.size = [10, 20, 810, 620]; self.alive = True
        self.ident = ("123456789", "c:\\fixture\\app.exe"); self.owner_ok = True
    @contextmanager
    def process(self, pid):
        self.calls.append("open")
        try: yield 1
        finally: self.calls.append("close")
    def live(self, handle): return self.alive
    def identity(self, handle): return self.ident
    def owns_window(self, hwnd, pid): return self.owner_ok
    def geometry(self, hwnd): return {"outer": list(self.size), "client": [0, 0, 780, 560], "dpi": 144}
    def resize(self, hwnd, width, height):
        self.calls.append("resize"); self.size = [10, 20, 10 + width, 20 + height]


class Controls(unittest.TestCase):
    def setUp(self):
        self.r = dict(desktop_name="Owned-Test", handle=123, pid=456, creation_filetime="123456789",
                      executable_path="C:\\fixture\\app.exe", expected_outer=[10,20,810,620], width=760,height=560)
    def test_positive(self):
        a=Fake(); result=m.resize_bound(self.r,a)
        self.assertTrue(result["ok"]); self.assertEqual(result["after"]["outer"],[10,20,770,580])
        self.assertEqual(a.calls,["open","resize","close"])
    def reject(self,r,a=None):
        a=a or Fake()
        with self.assertRaises(m.ResizeRejected): m.resize_bound(r,a)
        self.assertNotIn("resize",a.calls)
    def test_invalid_requests(self):
        for key,value in [("desktop_name","Default"),("desktop_name","WinSta0\\Other"),("handle",True),
                          ("pid",0),("width",0),("height",16385),("creation_filetime",123),("creation_filetime","0"),
                          ("executable_path","relative"),("expected_outer",[0,0,0,1])]:
            with self.subTest(key=key,value=value):
                r=copy.deepcopy(self.r);r[key]=value;self.reject(r)
        r=dict(self.r,unknown=True);self.reject(r)
    def test_stale_geometry(self):
        a=Fake();a.size=[0,0,800,600];self.reject(self.r,a);self.assertEqual(a.calls[-1],"close")
    def test_process_identity(self):
        for ident in [("987", "c:\\fixture\\app.exe"),("123456789","c:\\other.exe")]:
            a=Fake();a.ident=ident;self.reject(self.r,a)
    def test_dead_process(self):
        a=Fake();a.alive=False;self.reject(self.r,a)
    def test_wrong_desktop_window(self):
        a=Fake();a.owner_ok=False;self.reject(self.r,a)
    def test_deadline(self):
        a=Fake()
        with self.assertRaises(m.ResizeRejected):m.resize_bound(self.r,a,lambda:True)
        self.assertNotIn("resize",a.calls)

if __name__ == "__main__": unittest.main()
