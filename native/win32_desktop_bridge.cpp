#include <windows.h>

#include <cwchar>
#include <map>
#include <mutex>
#include <string>

namespace {

std::mutex g_desktop_mutex;
std::map<std::wstring, HDESK> g_desktops;

void write_message(wchar_t* output, unsigned long output_length, const std::wstring& message) {
    if (output == nullptr || output_length == 0) {
        return;
    }
    wcsncpy_s(output, output_length, message.c_str(), _TRUNCATE);
}

std::wstring format_error(const wchar_t* operation, DWORD code) {
    wchar_t* system_message = nullptr;
    const DWORD length = FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr,
        code,
        0,
        reinterpret_cast<wchar_t*>(&system_message),
        0,
        nullptr);
    std::wstring result(operation);
    result += L" failed (GetLastError=" + std::to_wstring(code) + L")";
    if (length != 0 && system_message != nullptr) {
        size_t message_length = wcslen(system_message);
        while (message_length > 0 && (system_message[message_length - 1] == L'\r' ||
                                      system_message[message_length - 1] == L'\n')) {
            system_message[--message_length] = L'\0';
        }
        result += L": ";
        result += system_message;
    }
    if (system_message != nullptr) {
        LocalFree(system_message);
    }
    return result;
}

bool valid_desktop_name(const wchar_t* name) {
    if (name == nullptr) {
        return false;
    }
    const size_t length = wcslen(name);
    if (length == 0 || length > 128) {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        const wchar_t character = name[index];
        if (character < 0x20 || character == L'\\' || character == L'/') {
            return false;
        }
    }
    return true;
}

HDESK get_or_open_desktop(const std::wstring& name, bool create, bool* already_exists, DWORD* error) {
    const auto found = g_desktops.find(name);
    if (found != g_desktops.end()) {
        if (already_exists != nullptr) {
            *already_exists = true;
        }
        return found->second;
    }

    HDESK desktop = OpenDesktopW(name.c_str(), 0, FALSE, GENERIC_ALL);
    if (desktop != nullptr) {
        g_desktops.emplace(name, desktop);
        if (already_exists != nullptr) {
            *already_exists = true;
        }
        return desktop;
    }

    if (!create) {
        if (error != nullptr) {
            *error = GetLastError();
        }
        return nullptr;
    }

    desktop = CreateDesktopW(name.c_str(), nullptr, nullptr, 0, GENERIC_ALL, nullptr);
    if (desktop == nullptr) {
        if (error != nullptr) {
            *error = GetLastError();
        }
        return nullptr;
    }
    g_desktops.emplace(name, desktop);
    if (already_exists != nullptr) {
        *already_exists = false;
    }
    return desktop;
}

}  // namespace

extern "C" __declspec(dllexport) unsigned long __cdecl ll_native_abi_version() {
    return 1;
}

extern "C" __declspec(dllexport) int __cdecl ll_desktop_create(
    const wchar_t* name,
    unsigned long long* handle,
    int* already_exists,
    wchar_t* error_message,
    unsigned long error_message_length) {
    if (!valid_desktop_name(name) || handle == nullptr || already_exists == nullptr) {
        write_message(error_message, error_message_length, L"Desktop name must be 1-128 characters without slashes or control characters.");
        return ERROR_INVALID_PARAMETER;
    }

    std::lock_guard<std::mutex> lock(g_desktop_mutex);
    bool existed = false;
    DWORD error = ERROR_SUCCESS;
    HDESK desktop = get_or_open_desktop(name, true, &existed, &error);
    if (desktop == nullptr) {
        write_message(error_message, error_message_length, format_error(L"CreateDesktopW/OpenDesktopW", error));
        return static_cast<int>(error);
    }
    *handle = reinterpret_cast<unsigned long long>(desktop);
    *already_exists = existed ? 1 : 0;
    return ERROR_SUCCESS;
}

extern "C" __declspec(dllexport) int __cdecl ll_desktop_launch(
    const wchar_t* name,
    const wchar_t* command_line,
    unsigned long input_idle_timeout_ms,
    unsigned long* process_id,
    unsigned long* thread_id,
    unsigned long* input_idle_result,
    wchar_t* error_message,
    unsigned long error_message_length) {
    if (!valid_desktop_name(name) || command_line == nullptr || command_line[0] == L'\0' ||
        process_id == nullptr || thread_id == nullptr || input_idle_result == nullptr) {
        write_message(error_message, error_message_length, L"Desktop name, command line, and result pointers are required.");
        return ERROR_INVALID_PARAMETER;
    }

    {
        std::lock_guard<std::mutex> lock(g_desktop_mutex);
        DWORD open_error = ERROR_SUCCESS;
        if (get_or_open_desktop(name, true, nullptr, &open_error) == nullptr) {
            write_message(error_message, error_message_length, format_error(L"CreateDesktopW/OpenDesktopW", open_error));
            return static_cast<int>(open_error);
        }
    }

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    const std::wstring desktop_path = L"WinSta0\\" + std::wstring(name);
    startup.lpDesktop = const_cast<wchar_t*>(desktop_path.c_str());
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_SHOWNORMAL;

    PROCESS_INFORMATION process{};
    std::wstring mutable_command(command_line);
    if (!CreateProcessW(
            nullptr,
            mutable_command.data(),
            nullptr,
            nullptr,
            FALSE,
            CREATE_NO_WINDOW,
            nullptr,
            nullptr,
            &startup,
            &process)) {
        const DWORD error = GetLastError();
        write_message(error_message, error_message_length, format_error(L"CreateProcessW", error));
        return static_cast<int>(error);
    }

    *process_id = process.dwProcessId;
    *thread_id = process.dwThreadId;
    *input_idle_result = WAIT_FAILED;
    if (input_idle_timeout_ms > 0) {
        SetLastError(ERROR_SUCCESS);
        const DWORD wait_result = WaitForInputIdle(process.hProcess, input_idle_timeout_ms);
        *input_idle_result = wait_result;
        if (wait_result == WAIT_FAILED) {
            const DWORD wait_error = GetLastError();
            // Console children have no GUI message queue. Their successful launch is still valid.
            if (wait_error != ERROR_NOT_GUI_PROCESS) {
                CloseHandle(process.hThread);
                CloseHandle(process.hProcess);
                write_message(error_message, error_message_length, format_error(L"WaitForInputIdle", wait_error));
                return static_cast<int>(wait_error);
            }
        }
    }

    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return ERROR_SUCCESS;
}

extern "C" __declspec(dllexport) int __cdecl ll_desktop_close(
    const wchar_t* name,
    int* closed,
    wchar_t* error_message,
    unsigned long error_message_length) {
    if (!valid_desktop_name(name) || closed == nullptr) {
        write_message(error_message, error_message_length, L"A valid desktop name and result pointer are required.");
        return ERROR_INVALID_PARAMETER;
    }

    std::lock_guard<std::mutex> lock(g_desktop_mutex);
    const auto found = g_desktops.find(name);
    if (found == g_desktops.end()) {
        *closed = 0;
        return ERROR_SUCCESS;
    }
    if (!CloseDesktop(found->second)) {
        const DWORD error = GetLastError();
        write_message(error_message, error_message_length, format_error(L"CloseDesktop", error));
        return static_cast<int>(error);
    }
    g_desktops.erase(found);
    *closed = 1;
    return ERROR_SUCCESS;
}
