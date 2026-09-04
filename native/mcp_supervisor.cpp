#include <windows.h>
#include <shellapi.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <string>
#include <thread>
#include <vector>

namespace {

constexpr DWORD kBufferSize = 64 * 1024;
constexpr size_t kMaxRestarts = 5;
constexpr auto kRestartWindow = std::chrono::seconds(60);

class Handle {
public:
    Handle() = default;
    explicit Handle(HANDLE value) : value_(value) {}
    ~Handle() { reset(); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&& other) noexcept : value_(other.release()) {}
    Handle& operator=(Handle&& other) noexcept {
        if (this != &other) {
            reset(other.release());
        }
        return *this;
    }
    HANDLE get() const { return value_; }
    HANDLE release() {
        HANDLE result = value_;
        value_ = nullptr;
        return result;
    }
    void reset(HANDLE value = nullptr) {
        if (value_ != nullptr && value_ != INVALID_HANDLE_VALUE) {
            CloseHandle(value_);
        }
        value_ = value;
    }
private:
    HANDLE value_ = nullptr;
};

bool write_all(HANDLE destination, const unsigned char* data, DWORD length) {
    DWORD total = 0;
    while (total < length) {
        DWORD written = 0;
        if (!WriteFile(destination, data + total, length - total, &written, nullptr) || written == 0) {
            return false;
        }
        total += written;
    }
    return true;
}

void pump(HANDLE source, HANDLE destination, std::atomic<bool>& open, bool close_destination) {
    std::vector<unsigned char> buffer(kBufferSize);
    while (open.load()) {
        DWORD read = 0;
        if (!ReadFile(source, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr) || read == 0 ||
            !write_all(destination, buffer.data(), read)) {
            open.store(false);
            break;
        }
    }
    if (close_destination) {
        CloseHandle(destination);
    }
}

std::wstring quote_argument(const std::wstring& argument) {
    if (!argument.empty() && argument.find_first_of(L" \t\"") == std::wstring::npos) {
        return argument;
    }
    std::wstring result(1, L'\"');
    size_t slashes = 0;
    for (const wchar_t character : argument) {
        if (character == L'\\') {
            ++slashes;
        } else if (character == L'\"') {
            result.append(slashes * 2 + 1, L'\\');
            result += L'\"';
            slashes = 0;
        } else {
            result.append(slashes, L'\\');
            slashes = 0;
            result += character;
        }
    }
    result.append(slashes * 2, L'\\');
    result += L'\"';
    return result;
}

std::wstring child_command_line() {
    int count = 0;
    wchar_t** arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (arguments == nullptr || count < 2) {
        if (arguments != nullptr) {
            LocalFree(arguments);
        }
        return {};
    }
    std::wstring result;
    for (int index = 1; index < count; ++index) {
        if (!result.empty()) {
            result += L' ';
        }
        result += quote_argument(arguments[index]);
    }
    LocalFree(arguments);
    return result;
}

int supervise(const std::wstring& command) {
    const HANDLE parent_input = GetStdHandle(STD_INPUT_HANDLE);
    const HANDLE parent_output = GetStdHandle(STD_OUTPUT_HANDLE);
    const HANDLE parent_error = GetStdHandle(STD_ERROR_HANDLE);
    if (parent_input == INVALID_HANDLE_VALUE || parent_output == INVALID_HANDLE_VALUE ||
        parent_error == INVALID_HANDLE_VALUE) {
        return ERROR_INVALID_HANDLE;
    }

    std::vector<std::chrono::steady_clock::time_point> restarts;
    for (;;) {
        SECURITY_ATTRIBUTES attributes{sizeof(attributes), nullptr, TRUE};
        HANDLE input_read_raw = nullptr;
        HANDLE input_write_raw = nullptr;
        HANDLE output_read_raw = nullptr;
        HANDLE output_write_raw = nullptr;
        if (!CreatePipe(&input_read_raw, &input_write_raw, &attributes, 0)) {
            return static_cast<int>(GetLastError());
        }
        Handle input_read(input_read_raw);
        Handle input_write(input_write_raw);
        if (!SetHandleInformation(input_write.get(), HANDLE_FLAG_INHERIT, 0) ||
            !CreatePipe(&output_read_raw, &output_write_raw, &attributes, 0)) {
            return static_cast<int>(GetLastError());
        }
        Handle output_read(output_read_raw);
        Handle output_write(output_write_raw);
        if (!SetHandleInformation(output_read.get(), HANDLE_FLAG_INHERIT, 0)) {
            return static_cast<int>(GetLastError());
        }

        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        startup.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
        startup.wShowWindow = SW_HIDE;
        startup.hStdInput = input_read.get();
        startup.hStdOutput = output_write.get();
        startup.hStdError = parent_error;
        PROCESS_INFORMATION process{};
        std::wstring mutable_command = command;
        if (!CreateProcessW(nullptr, mutable_command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                            nullptr, nullptr, &startup, &process)) {
            return static_cast<int>(GetLastError());
        }
        Handle process_handle(process.hProcess);
        Handle thread_handle(process.hThread);
        input_read.reset();
        output_write.reset();

        std::atomic<bool> input_open{true};
        std::atomic<bool> output_open{true};
        const HANDLE child_input = input_write.release();
        std::thread inbound(pump, parent_input, child_input, std::ref(input_open), true);
        std::thread outbound(pump, output_read.get(), parent_output, std::ref(output_open), false);
        WaitForSingleObject(process_handle.get(), INFINITE);
        DWORD exit_code = 1;
        GetExitCodeProcess(process_handle.get(), &exit_code);
        input_open.store(false);
        CancelSynchronousIo(inbound.native_handle());
        inbound.join();
        // The child closing its inherited stdout pipe produces EOF. Let the
        // output pump drain every final protocol byte before joining it.
        outbound.join();

        if (exit_code == 0 || GetFileType(parent_input) == FILE_TYPE_UNKNOWN) {
            return static_cast<int>(exit_code);
        }
        const auto now = std::chrono::steady_clock::now();
        restarts.erase(std::remove_if(restarts.begin(), restarts.end(), [&](const auto& time) {
            return now - time > kRestartWindow;
        }), restarts.end());
        if (restarts.size() >= kMaxRestarts) {
            return static_cast<int>(exit_code);
        }
        restarts.push_back(now);
        const auto exponent = std::min<size_t>(restarts.size() - 1, 4);
        std::this_thread::sleep_for(std::chrono::milliseconds(250u << exponent));
    }
}

}  // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    const std::wstring command = child_command_line();
    return command.empty() ? ERROR_INVALID_PARAMETER : supervise(command);
}
