/* Phase 0 probe v2: 观察 FreeRDP 解析 .rdp 文件的实际效果
 * 编译: gcc -O1 probe.c -o probe -I/usr/include/freerdp3 -I/usr/include/winpr3 \
 *               -lfreerdp3 -lfreerdp-client3 -lwinpr3
 */
#define _GNU_SOURCE
#include <freerdp/freerdp.h>
#include <freerdp/settings.h>
#include <freerdp/client/file.h>
#include <winpr/wlog.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define MAXKEY 5400

static BOOL raw_cb(void* ctx, const char* key, char type, const char* value)
{
    (void)ctx;
    printf("RAW\t%s\t%c\t%s\n", key, type, value ? value : "(null)");
    return TRUE;
}

static const char* tname(SSIZE_T k)
{
    const char* n = freerdp_settings_get_type_name_for_key(k);
    return n ? n : "?";
}

/* 用正确的 getter 取值，统一格式化成字符串，避免跨类型比较的错误 */
static void snprint_val(const rdpSettings* s, SSIZE_T k, const char* t, char* out, size_t n)
{
    if (strstr(t, "BOOL"))
        snprintf(out, n, "%s", freerdp_settings_get_bool(s, k) ? "TRUE" : "FALSE");
    else if (strstr(t, "UINT32"))
        snprintf(out, n, "%u", freerdp_settings_get_uint32(s, k));
    else if (strstr(t, "UINT16"))
        snprintf(out, n, "%u", freerdp_settings_get_uint16(s, k));
    else if (strstr(t, "INT32"))
        snprintf(out, n, "%d", freerdp_settings_get_int32(s, k));
    else if (strstr(t, "INT16"))
        snprintf(out, n, "%d", freerdp_settings_get_int16(s, k));
    else if (strstr(t, "UINT64"))
        snprintf(out, n, "%llu", (unsigned long long)freerdp_settings_get_uint64(s, k));
    else if (strstr(t, "INT64"))
        snprintf(out, n, "%lld", (long long)freerdp_settings_get_int64(s, k));
    else if (strstr(t, "STRING"))
    {
        const char* v = freerdp_settings_get_string(s, k);
        snprintf(out, n, "%s", v ? v : "<null>");
    }
    else
        snprintf(out, n, "<%s>", t);
}

static void diff_settings(const rdpSettings* a, const rdpSettings* b)
{
    printf("=== 由 .rdp 改变的 setting ===\n");
    int count = 0;
    for (SSIZE_T k = 0; k < MAXKEY; k++)
    {
        const char* name = freerdp_settings_get_name_for_key(k);
        if (!name)
            continue;
        const char* t = tname(k);
        if (strstr(t, "POINTER") || strcmp(t, "?") == 0)
            continue; /* 指针类型是堆地址噪声 */

        char va[512], vb[512];
        snprint_val(a, k, t, va, sizeof(va));
        snprint_val(b, k, t, vb, sizeof(vb));
        if (strcmp(va, vb) == 0)
            continue;
        printf("  %-40s %-10s %s -> %s\n", name, t + 22, va, vb);
        count++;
    }
    printf("=== end (%d 项) ===\n", count);
}

static void dump_settings(const rdpSettings* s)
{
    for (SSIZE_T k = 0; k < MAXKEY; k++)
    {
        const char* name = freerdp_settings_get_name_for_key(k);
        if (!name)
            continue;
        const char* t = tname(k);
        if (strstr(t, "POINTER") || strcmp(t, "?") == 0)
            continue;
        char v[512];
        snprint_val(s, k, t, v, sizeof(v));
        printf("S\t%s\t%s\t%s\n", name, t, v);
    }
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        fprintf(stderr, "usage: %s <file.rdp> [--raw|--dump]\n", argv[0]);
        return 2;
    }
    const BOOL doDump = (argc > 2 && strcmp(argv[2], "--dump") == 0);
    WLog_SetLogLevel(WLog_GetRoot(), WLOG_OFF);

    rdpFile* f = freerdp_client_rdp_file_new();
    if (!f)
        return 3;

    BOOL ok;
    if (argc > 2 && strcmp(argv[2], "--raw") == 0)
        ok = freerdp_client_parse_rdp_file_ex(f, argv[1], raw_cb);
    else
        ok = freerdp_client_parse_rdp_file(f, argv[1]);
    if (doDump && !ok)
        return 1;
    printf("parse_ok=%s\n", ok ? "TRUE" : "FALSE");
    if (!ok)
    {
        freerdp_client_rdp_file_free(f);
        return 1;
    }

    rdpSettings* a = freerdp_settings_new(0);
    rdpSettings* b = freerdp_settings_new(0);
    if (!a || !b)
        return 3;

    BOOL pok = freerdp_client_populate_settings_from_rdp_file(f, b);
    printf("populate_ok=%s\n", pok ? "TRUE" : "FALSE");

    if (doDump)
    {
        dump_settings(b);
        freerdp_settings_free(a);
        freerdp_settings_free(b);
        freerdp_client_rdp_file_free(f);
        return 0;
    }

    const char* probeKeys[] = { "full address", "server port", "redirectclipboard",
                                "disableclipboardredirection", "redirectprinters",
                                "disableprinterredirection", "drivestoredirect",
                                "selectedmonitors", "authentication level",
                                "gui_custom_key", "password", "screen mode id" };
    printf("=== rdp_file 内存储（int 为 -1 表示该键不存在于文件）===\n");
    for (size_t i = 0; i < sizeof(probeKeys) / sizeof(*probeKeys); i++)
    {
        int v = freerdp_client_rdp_file_get_integer_option(f, probeKeys[i]);
        const char* s = freerdp_client_rdp_file_get_string_option(f, probeKeys[i]);
        printf("  %-30s int=%-6d str=%s\n", probeKeys[i], v, s ? s : "(null)");
    }

    diff_settings(a, b);

    freerdp_settings_free(a);
    freerdp_settings_free(b);
    freerdp_client_rdp_file_free(f);
    return 0;
}
