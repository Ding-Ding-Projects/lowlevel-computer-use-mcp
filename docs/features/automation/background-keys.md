# Background navigation keys

The `win_send_keys` route posts keyboard messages to the explicitly selected window or child control without changing the visible desktop focus. Enhanced navigation keys preserve their extended scan-code identity: Page Up/Down, Home/End, Insert/Delete and the arrow cluster must not be confused with numeric-keypad keys.

The sender uses `MapVirtualKeyW(..., MAPVK_VK_TO_VSC_EX)`, stores only the scan-code byte in bits 16–23, and maps an E0 prefix to bit 24 in both key-down and key-up messages. Some layouts return only the scan-code byte even in this mode, so dedicated extended virtual keys also set bit 24 explicitly. Release messages also retain the previous-state and transition flags. Ordinary keys retain a clear extended flag.

The caller must still identify the target and verify the resulting state. Posted modifier combinations can be ignored by programs that inspect physical keyboard state. This change does not activate a window, inject foreground input or claim universal keyboard compatibility.

## Verification

Four focused regressions cover prefixed and prefix-free extended mappings, ordinary keys and exact target/message delivery. The original implementation failed thirteen assertions. The first repair still failed ten prefix-free assertions; the corrected implementation passes all four tests.

Source `5012390519d7b2a396510e46567e9fabcf1a7135` passed `build.bat /s -EnvironmentPath .bootstrap/navigation-verification-venv`. The rebuilt persistent loopback compatibility HTTP server then delivered Tab, Page Down and text entry to real Material System Care Services, Scheduled tasks and Processes views at 800 × 600 with doubled bilingual text. All three scrolled to lower controls and accepted search text. Their recorded processes exited and their hidden desktops were closed. Painted Flutter observations are separate from native-compositor and physical-DPI proof.

## 中文說明

背景鍵盤訊息會保留導覽鍵的延伸掃描碼，避免 Page Down 等按鍵被當成數字鍵盤按鍵。此功能不會切換可見桌面的焦點；呼叫端仍須核對實際操作結果。四項指定回歸測試已通過。重建伺服器已在三個實際工作區完成 Tab、Page Down 及搜尋輸入驗證；相關程序及隱藏桌面均已結束。Flutter 繪製畫面不等同原生合成器或實體 DPI 證據。

References: [Keyboard input](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-keyboard-input), [MapVirtualKeyW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mapvirtualkeyw).
