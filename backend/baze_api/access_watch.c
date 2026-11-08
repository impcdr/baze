/* Logs attempts to open private files. The path is recorded. The bytes are not. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/stat.h>
#include <unistd.h>

static int (*real_open)(const char *, int, ...);
static int (*real_open64)(const char *, int, ...);
static int (*real_openat)(int, const char *, int, ...);
static int (*real_openat64)(int, const char *, int, ...);
static int (*real_connect)(int, const struct sockaddr *, socklen_t);
static int logfd = -1;

static void put_num(char *buf, size_t *used, unsigned value) {
    char tmp[8];
    int n = 0;
    if (value == 0) tmp[n++] = '0';
    while (value && n < 8) {
        tmp[n++] = (char)('0' + (value % 10));
        value /= 10;
    }
    while (n > 0 && *used + 2 < 480) buf[(*used)++] = tmp[--n];
}

static int starts(const char *path, const char *root) {
    size_t n = strlen(root);
    return strncmp(path, root, n) == 0 && (path[n] == '\0' || path[n] == '/');
}

static int high(const char *path) {
    return strstr(path, "/etc/shadow") || strstr(path, "/etc/gshadow") || strstr(path, "docker.sock") ||
           strstr(path, "/.ssh") || strstr(path, "id_rsa") || strstr(path, "id_ed25519") ||
           strstr(path, "id_ecdsa") || strstr(path, "/.aws/") || strstr(path, "/.gnupg") ||
           strstr(path, "/.kube/") || strstr(path, "/.azure/") || strstr(path, "/.netrc") ||
           strstr(path, "/.npmrc") || strstr(path, "/.pypirc") || strstr(path, "git-credentials") ||
           strstr(path, "/credentials");
}

static int secret(const char *path) {
    int boxed;
    if (!path || !path[0]) return 0;
    if (starts(path, "/usr") || starts(path, "/lib") || starts(path, "/lib64") || starts(path, "/bin") ||
        starts(path, "/sbin") || starts(path, "/tmp") || starts(path, "/specimen") || starts(path, "/etc/hermes"))
        return 0;
    if (strstr(path, "baze-access") || strstr(path, "access.log")) return 0;
    boxed = starts(path, "/opt/data") || starts(path, "/opt/hermes");
    if (boxed) return high(path);
    if (starts(path, "/run")) return strstr(path, "docker.sock") != NULL;
    if (starts(path, "/proc")) return strstr(path, "/environ") != NULL;
    if (high(path) || strstr(path, ".env") || strstr(path, "cookies")) return 1;
    return 0;
}

static void note(const char *path) {
    char buf[480];
    size_t used = 0;
    const char *prefix = "open ";
    if (logfd < 0 || !secret(path)) return;
    while (*prefix && used + 2 < sizeof buf) buf[used++] = *prefix++;
    while (*path && used + 2 < sizeof buf) buf[used++] = *path++;
    buf[used++] = '\n';
    (void)write(logfd, buf, used);
}

static void note_connect(int fd, const struct sockaddr *addr) {
    char buf[480];
    size_t used = 0;
    const unsigned char *ip;
    unsigned port;
    int type = 0;
    socklen_t type_len = sizeof type;
    const char *prefix = "connect ";
    const char *proto = "TCP";
    if (logfd < 0 || !addr || addr->sa_family != AF_INET) return;
    ip = (const unsigned char *)&((const struct sockaddr_in *)addr)->sin_addr;
    port = ntohs(((const struct sockaddr_in *)addr)->sin_port);
    if (port == 53 || port == 8001 || ip[0] == 127) return;
    if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &type_len) == 0 && type == SOCK_DGRAM) proto = "UDP";
    while (*prefix && used + 2 < sizeof buf) buf[used++] = *prefix++;
    while (*proto && used + 2 < sizeof buf) buf[used++] = *proto++;
    buf[used++] = ' ';
    put_num(buf, &used, ip[0]); buf[used++] = '.';
    put_num(buf, &used, ip[1]); buf[used++] = '.';
    put_num(buf, &used, ip[2]); buf[used++] = '.';
    put_num(buf, &used, ip[3]);
    prefix = " port ";
    while (*prefix && used + 2 < sizeof buf) buf[used++] = *prefix++;
    put_num(buf, &used, port);
    buf[used++] = '\n';
    (void)write(logfd, buf, used);
}

__attribute__((constructor)) static void baze_access_init(void) {
    const char *path = getenv("BAZE_ACCESS_LOG");
    if (!path || !path[0]) path = "/opt/data/app/access.log";
    real_open = dlsym(RTLD_NEXT, "open");
    real_open64 = dlsym(RTLD_NEXT, "open64");
    real_openat = dlsym(RTLD_NEXT, "openat");
    real_openat64 = dlsym(RTLD_NEXT, "openat64");
    real_connect = dlsym(RTLD_NEXT, "connect");
    if (!real_open) return;
    logfd = real_open(path, O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (logfd >= 0) fchmod(logfd, 0666);
}

int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    note(path);
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    note(path);
    if (!real_open64) return open(path, flags, mode);
    return real_open64(path, flags, mode);
}

int openat(int dirfd, const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    note(path);
    return real_openat(dirfd, path, flags, mode);
}

int openat64(int dirfd, const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    note(path);
    if (!real_openat64) return openat(dirfd, path, flags, mode);
    return real_openat64(dirfd, path, flags, mode);
}

int connect(int fd, const struct sockaddr *addr, socklen_t len) {
    note_connect(fd, addr);
    if (!real_connect) {
        errno = EIO;
        return -1;
    }
    return real_connect(fd, addr, len);
}
