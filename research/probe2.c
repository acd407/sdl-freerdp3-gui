/* 用**真实客户端的解析入口**验证：.rdp 文件里的键与命令行开关是否等效。
 * 编译: gcc -O1 -w probe2.c -o probe2 -I/usr/include/freerdp3 -I/usr/include/winpr3 \
 *              -lfreerdp3 -lfreerdp-client3 -lwinpr3
 * 用法: ./probe2 <file.rdp> [额外参数...]
 */
#define _GNU_SOURCE
#include <freerdp/freerdp.h>
#include <freerdp/settings.h>
#include <freerdp/client.h>
#include <freerdp/client/cmdline.h>
#include <winpr/wlog.h>

#include <stdio.h>
#include <string.h>

static const char* tname(SSIZE_T k)
{
    const char* n = freerdp_settings_get_type_name_for_key(k);
    return n ? n : "?";
}

static void show(const rdpSettings* s, const char* name)
{
    const SSIZE_T k = freerdp_settings_get_key_for_name(name);
    if (k < 0)
    {
        printf("  %-34s <无此 setting>\n", name);
        return;
    }
    const char* t = tname(k);
    printf("  %-34s ", name);
    if (strstr(t, "BOOL"))
        printf("%s\n", freerdp_settings_get_bool(s, k) ? "TRUE" : "FALSE");
    else if (strstr(t, "UINT32"))
        printf("%u\n", freerdp_settings_get_uint32(s, k));
    else if (strstr(t, "STRING"))
    {
        const char* v = freerdp_settings_get_string(s, k);
        printf("%s\n", v ? v : "(null)");
    }
    else
        printf("<%s>\n", t);
}

static void report(const rdpSettings* s, const char* title)
{
    printf("\n=== %s ===\n", title);
    const char* keys[] = { "FreeRDP_DynamicResolutionUpdate", "FreeRDP_SupportDisplayControl",
                           "FreeRDP_SmartSizing",           "FreeRDP_AuthenticationLevel",
                           "FreeRDP_NlaSecurity",           "FreeRDP_TlsSecurity",
                           "FreeRDP_RdpSecurity",           "FreeRDP_ExtSecurity",
                           "FreeRDP_ServerHostname",        "FreeRDP_ServerPort",
                           "FreeRDP_ConnectionType",        "FreeRDP_RedirectClipboard",
                           "FreeRDP_NegotiateSecurityLayer", "FreeRDP_DisableCredentialsDelegation",
                           "FreeRDP_AudioPlayback", "FreeRDP_RemoteConsoleAudio",
                           "FreeRDP_SoundBeepsEnabled", "FreeRDP_AudioCapture" };
    for (size_t i = 0; i < sizeof(keys) / sizeof(*keys); i++)
        show(s, keys[i]);
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        fprintf(stderr, "usage: %s <file.rdp> [args...]\n", argv[0]);
        return 2;
    }
    WLog_SetLogLevel(WLog_GetRoot(), WLOG_OFF);

    /* 复刻真实客户端的调用：sdl-freerdp3 <file.rdp> [args...] */
    char* av[64];
    int n = 0;
    av[n++] = (char*)"sdl-freerdp3";
    av[n++] = argv[1];
    for (int i = 2; i < argc && n < 63; i++)
        av[n++] = argv[i];
    av[n] = NULL;

    rdpSettings* s = freerdp_settings_new(0);
    const int rc = freerdp_client_settings_parse_command_line_ex(s, n, av, FALSE, NULL, 0, NULL,
                                                                 NULL);
    printf("parse_command_line_ex rc=%d (0=成功)\n", rc);

    char title[512];
    snprintf(title, sizeof(title), "argv:");
    for (int i = 1; i < n; i++)
    {
        strncat(title, " ", sizeof(title) - strlen(title) - 1);
        strncat(title, av[i], sizeof(title) - strlen(title) - 1);
    }
    report(s, title);

    freerdp_settings_free(s);
    return 0;
}
