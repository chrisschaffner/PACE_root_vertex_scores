METIS_PREFIX := $(shell brew --prefix metis)

CC = clang
CFLAGS = -O3 -g -Wall -Wpedantic -Werror=vla
INCLUDES = -I../include -I$(METIS_PREFIX)/include
LIBS = -L$(METIS_PREFIX)/lib -lmetis -lm

all: solve

solve: solve.c naurng.c ../include/bitset.h
	$(CC) $(CFLAGS) $(INCLUDES) -o solve solve.c naurng.c $(LIBS)

clean:
	rm -f solve