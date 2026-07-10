#define _XOPEN_SOURCE 600

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/types.h>
#include <unistd.h>

// #include "tree_sitter/alloc.h"
// #include "tree_sitter/array.h"
#include "tree_sitter/parser.h"

#include "scanner_tokens.h"

#define BUF_SZ 0x40000
#define FIFO_BS_IN "/tmp/bs.in"
#define FIFO_BS_OUT "/tmp/bs.out"
#define TS_BIN "/tmp/ts.bin"
#define TS_ERR "/tmp/ts.err"
#define TS_OUT "/tmp/ts.out"

uint8_t _buf[BUF_SZ];
uint32_t _ofs[2 * BUF_SZ];
uint32_t _ofs_i = 0;
uint32_t _ofs_n = 0;

int _bs_in = -1;
int _bs_out = -1;
FILE *_ts_err = NULL;
FILE *_ts_out = NULL;

static ssize_t read_k(int fd, void *buf, size_t k) {
    size_t total = 0;
    char *p = buf;
    while (total < k) {
        ssize_t n = read(fd, p + total, k - total);
        if (n > 0) {
            total += n;
        } else if (n == 0) {
            // If writer closed pipe, we might still
            // have data to read, so assume we read it.
            total += k;
        } else if (errno == EINTR) {
            fprintf(_ts_err, "Read EINTR.\n");
            continue;
        } else {
            fprintf(_ts_err, "read: %s.", strerror(errno));
            return -1;
        }
    }

    return total;
}

int read_offsets(void) {
    _bs_out = open(FIFO_BS_OUT, O_RDONLY);
    if (_bs_out == -1) {
        fprintf(_ts_err, "err open '%s': %s.\n", FIFO_BS_OUT, strerror(errno));
        exit(EXIT_FAILURE);
    }
    fprintf(_ts_out, "Polling '%s'.\n", FIFO_BS_OUT);

    int i = 0;
    int acc_n = 0;
    uint32_t sz = -1;
    while (sz == -1 || acc_n < sz) {
        uint32_t val = 0;
        ssize_t n = read_k(_bs_out, &val, sizeof(val));
        if (n != sizeof(val)) {
            fprintf(_ts_err,
                    "Incomplete read '%08x': expected '%ld', got '%ld'.\n",
                    val,
                    sizeof(val),
                    n);
            return -1;
        }

        uint32_t val32 = ntohl(val);
        fprintf(_ts_out, "Read: '%08x'.\n", val32);

        if (sz == -1) {
            fprintf(_ts_out, "Size: %u (0x%08x).\n", val32, val32);
            sz = val32;
        } else {
            acc_n += n;
            fprintf(_ts_out,
                    "ofs[%d (0x%08x)]: %u (0x%08x) [%d/%d].\n",
                    i,
                    i,
                    val32,
                    val32,
                    acc_n,
                    sz);
            _ofs[i++] = val32;
        }
    }
    fprintf(_ts_out, "Total: %u (0x%08x).\n", i, i);
    _ofs_n = i;

    if (_bs_out != -1 && close(_bs_out) != 0) {
        fprintf(_ts_err, "err close: %s.", strerror(errno));
        exit(EXIT_FAILURE);
    }

    return 0;
}

void dump(TSLexer *lexer) {
    FILE *bin = fopen(TS_BIN, "wb");
    if (bin == NULL) {
        fprintf(_ts_err, "err fopen '%s': %s.\n", TS_BIN, strerror(errno));
        exit(EXIT_FAILURE);
    }

    uint32_t k = 0;
    while (!lexer->eof(lexer)) {
        const uint32_t c32 = lexer->lookahead;
        if ((c32 & 0xffffff00UL) != 0) {
            fprintf(_ts_err, "bad lookahead: '%08x'.\n", c32);
            exit(EXIT_FAILURE);
        }

        const uint8_t c = c32 & 0xff;
        _buf[k++] = c;
        fprintf(_ts_out, "%08x\n", c);

        lexer->advance(lexer, false);
    }
    fprintf(_ts_out, "Total: %u (0x%08x).\n", k, k);

    _bs_in = open(FIFO_BS_IN, O_WRONLY);
    if (_bs_in == -1) {
        fprintf(_ts_err, "err open '%s': %s.\n", FIFO_BS_IN, strerror(errno));
        exit(EXIT_FAILURE);
    }
    ssize_t n = write(_bs_in, &k, sizeof(k));
    if (n != sizeof(k)) {
        fprintf(_ts_err,
                "err write '%s': '%lu != %ld'.\n",
                FIFO_BS_IN,
                n,
                sizeof(k));
        exit(EXIT_FAILURE);
    }
    n = write(_bs_in, &_buf, sizeof(_buf[0]) * k);
    if (n != sizeof(_buf[0]) * k) {
        fprintf(_ts_err,
                "err write '%s': '%lu != %ld'.\n",
                FIFO_BS_IN,
                n,
                sizeof(_buf[0]) * k);
        exit(EXIT_FAILURE);
    }

    if ((fflush(bin) == -1) || (fflush(_ts_out) == -1)) {
        fprintf(_ts_err, "err fflush: %s.", strerror(errno));
        exit(EXIT_FAILURE);
    }
    if ((fsync(fileno(bin)) == -1) || (fsync(fileno(_ts_out)) == -1)) {
        fprintf(_ts_err, "err fsync: %s.", strerror(errno));
        exit(EXIT_FAILURE);
    }
    if (fclose(bin) != 0) {
        fprintf(_ts_err, "err fclose: %s.", strerror(errno));
        exit(EXIT_FAILURE);
    }
    if (_bs_in != -1 && close(_bs_in) != 0) {
        fprintf(_ts_err, "err close: %s.", strerror(errno));
        exit(EXIT_FAILURE);
    }
}

static int _x = 0;

bool tree_sitter_elf_external_scanner_scan(void *payload,
                                            TSLexer *lexer,
                                            const bool *valid_symbols) {
    if (_ts_out == NULL) {
        fprintf(_ts_err, "err out null.\n");
        exit(EXIT_FAILURE);
    }
    fprintf(_ts_out,
            "%d: %d%d%d\n",
            _x,
            valid_symbols[PAD],
            valid_symbols[PAD0],
            valid_symbols[ERR]);
    if (fflush(_ts_out) == -1) {
        fprintf(_ts_err, "err fflush.\n");
        exit(EXIT_FAILURE);
    }
    if (fsync(fileno(_ts_out)) == -1) {
        fprintf(_ts_err, "err fsync.\n");
        exit(EXIT_FAILURE);
    }

    if (_x == 0) {
        _x++;

        lexer->mark_end(lexer);
        dump(lexer);
        read_offsets();
        lexer->result_symbol = PAD0;
        return true;
    }

    if (_ofs_i >= _ofs_n) {
        fprintf(_ts_err, "err ofs_i '%d' >= '%d'.\n", _ofs_i, _ofs_n);
        
		// Maybe it's trailing data?
        while (!lexer->eof(lexer)) {
            lexer->advance(lexer, false);
        }
        lexer->mark_end(lexer);
        lexer->result_symbol = PAD;
        return true;
    }

    uint32_t sz = _ofs[_ofs_i++];
    if (sz == 0) {
        fprintf(_ts_err, "err sz == 0.\n");
        exit(EXIT_FAILURE);
    }
    for (int i = 0; i < sz; i++) {
        lexer->advance(lexer, false);
    }

    uint32_t sym = _ofs[_ofs_i++];
    if (sym >= ERR) {
        fprintf(_ts_err, "err token type '%d' >= ERR.\n", sym);
        exit(EXIT_FAILURE);
    }
    fprintf(_ts_out,
            "@ ofs_i='%d': sz='0x%04x', sym='0x%04x'.\n",
            _ofs_i,
            sz,
            sym);
    lexer->mark_end(lexer);
    lexer->result_symbol = sym;
    return true;
}

void *tree_sitter_elf_external_scanner_create() {
    if (_ts_err == NULL) {
        _ts_err = fopen(TS_ERR, "w");
        if (_ts_err == NULL) {
            fprintf(_ts_err, "err fopen.\n");
            exit(EXIT_FAILURE);
        }
    }
    if (_ts_out == NULL) {
        _ts_out = fopen(TS_OUT, "w");
        if (_ts_out == NULL) {
            fprintf(_ts_err, "err fopen.\n");
            exit(EXIT_FAILURE);
        }
    }

    return NULL;
}

void tree_sitter_elf_external_scanner_destroy(void *payload) {
    if (_bs_in != -1 && close(_bs_in) != 0) {
        fprintf(_ts_err, "err close '%s': %s.", FIFO_BS_IN, strerror(errno));
        exit(EXIT_FAILURE);
    }
    if (_bs_out != -1 && close(_bs_out) != 0) {
        fprintf(_ts_err, "err close '%s': %s.", FIFO_BS_OUT, strerror(errno));
        exit(EXIT_FAILURE);
    }
    if (_ts_err != NULL && fclose(_ts_err) != 0) {
        fprintf(stderr, "err fclose.\n");
        exit(EXIT_FAILURE);
    }
    if (_ts_out != NULL && fclose(_ts_out) != 0) {
        fprintf(stderr, "err fclose.\n");
        exit(EXIT_FAILURE);
    }
}

unsigned tree_sitter_elf_external_scanner_serialize(void *payload,
                                                     char *buffer) {
    return 0;
}
void tree_sitter_elf_external_scanner_deserialize(void *payload,
                                                   char *buffer,
                                                   unsigned length) {}
