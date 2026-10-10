# Background navigation keys

The `win_send_keys` route posts keyboard messages to the explicitly selected window or child control without changing the visible desktop focus. Enhanced navigation keys preserve their extended scan-code identity: Page Up/Down, Home/End, Insert/Delete and the arrow cluster must not be confused with numeric-keypad keys.

The sender uses `MapVirtualKeyW(..., MAPVK_VK_TO_VSC_EX)`, stores only the scan-code byte in bits 16–23, and maps an E0 prefix to bit 24 in both key-down and key-up messages. Release messages also retain the previous-state and transition flags. Ordinary keys retain a clear extended flag.

The caller must still identify the target and verify the resulting state. Posted modifier combinations can be ignored by programs that inspect physical keyboard state. This change does not activate a window, inject foreground input or claim universal keyboard compatibility.

## Verification

Three focused regressions cover twelve extended mappings, ordinary keys and exact target/message delivery. The old implementation failed thirteen assertions; the corrected implementation passes. A real hidden Flutter view moved after an explicitly encoded extended Page Down message; verification through the rebuilt persistent server remains pending.

## 中文說明

背景鍵盤訊息會保留導覽鍵的延伸掃描碼，避免 Page Down 等按鍵被當成數字鍵盤按鍵。此功能不會切換可見桌面的焦點；呼叫端仍須核對實際操作結果。三項指定回歸測試已通過，重建伺服器的實際操作驗證仍待完成。

References: [Keyboard input](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-keyboard-input), [MapVirtualKeyW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mapvirtualkeyw).
