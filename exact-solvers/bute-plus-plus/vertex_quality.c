#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/wait.h>
#include <errno.h>

/* Usage: ./vertex_quality ./bute-plus-plus < graph.gr > scores.csv
   POSIX implementation; calls the unmodified exact solver on each connected
   component of G-v.  A failed solver call aborts label generation. */

typedef struct { int n; unsigned char *a; } Graph;
static void die(const char *msg) { fprintf(stderr,"Error: %s\n",msg); exit(EXIT_FAILURE); }
static Graph new_graph(int n) {
    if (n < 0 || (size_t)n > ((size_t)-1)/(size_t)(n ? n : 1)) die("invalid graph size");
    Graph g={n,calloc((size_t)n*(size_t)n,1)};
    if (!g.a) die("allocation failed");
    return g;
}
static int exact_depth(const char *solver, const Graph *g, const int *verts, int k) {
    if (!k) return 0;
    if (k==1) return 1;
    FILE *input=tmpfile(), *output=tmpfile();
    if (!input || !output) die("tmpfile failed");
    int edges=0;
    for(int i=0;i<k;i++) for(int j=i+1;j<k;j++)
        if(g->a[(size_t)verts[i]*g->n+verts[j]]) edges++;
    fprintf(input,"p tdp %d %d\n",k,edges);
    for(int i=0;i<k;i++) for(int j=i+1;j<k;j++)
        if(g->a[(size_t)verts[i]*g->n+verts[j]]) fprintf(input,"%d %d\n",i+1,j+1);
    fflush(input); rewind(input);
    pid_t pid=fork();
    if(pid<0) die("fork failed");
    if(pid==0) {
        if(dup2(fileno(input),STDIN_FILENO)<0 || dup2(fileno(output),STDOUT_FILENO)<0) _exit(126);
        fclose(input); fclose(output);
        execlp(solver,solver,(char*)NULL);
        _exit(127);
    }
    int status;
    while(waitpid(pid,&status,0)<0) { if(errno!=EINTR) die("waitpid failed"); }
    rewind(output);
    int depth=-1;
    int read_ok=fscanf(output,"%d",&depth);
    fclose(input); fclose(output);
    if(!WIFEXITED(status)||WEXITSTATUS(status)!=0||read_ok!=1||depth<1||depth>k)
        die("exact solver failed or returned invalid depth");
    return depth;
}
int main(int argc,char **argv) {
    if(argc!=2) { fprintf(stderr,"Usage: %s SOLVER < graph.gr > scores.csv\n",argv[0]); return 2; }
    char line[4096]; Graph g={0,NULL}; int declared_edges=-1,edges=0;
    while(fgets(line,sizeof line,stdin)) {
        if(line[0]=='c'||line[0]=='\n'||line[0]=='\r') continue;
        if(line[0]=='p') {
            char type[32]; int n,m;
            if(g.a||sscanf(line,"p %31s %d %d",type,&n,&m)!=3||strcmp(type,"tdp")||n<=0||m<0) die("invalid header");
            g=new_graph(n); declared_edges=m;
        } else {
            int u,v;
            if(!g.a||sscanf(line,"%d %d",&u,&v)!=2||u<1||v<1||u>g.n||v>g.n) die("invalid edge");
            --u; --v;
            if(u!=v&&!g.a[(size_t)u*g.n+v]) {
                g.a[(size_t)u*g.n+v]=g.a[(size_t)v*g.n+u]=1;
                edges++;
            }
        }
    }
    if(!g.a) die("missing graph header");
    if(edges!=declared_edges) fprintf(stderr,"Warning: %d unique edges; header declares %d\n",edges,declared_edges);
    int *queue=malloc((size_t)g.n*sizeof(int));
    int *component=malloc((size_t)g.n*sizeof(int));
    unsigned char *seen=malloc((size_t)g.n);
    if(!queue||!component||!seen) die("allocation failed");
    printf("vertex,quality\n");
    for(int root=0;root<g.n;root++) {
        memset(seen,0,(size_t)g.n); seen[root]=1;
        int worst=0;
        for(int start=0;start<g.n;start++) {
            if(seen[start]) continue;
            int head=0,tail=0,k=0;
            seen[start]=1; queue[tail++]=start;
            while(head<tail) {
                int u=queue[head++]; component[k++]=u;
                for(int v=0;v<g.n;v++) if(!seen[v]&&g.a[(size_t)u*g.n+v]) {
                    seen[v]=1; queue[tail++]=v;
                }
            }
            int d=exact_depth(argv[1],&g,component,k);
            if(d>worst) worst=d;
        }
        printf("%d,%d\n",root+1,worst+1);
        fflush(stdout);
        fprintf(stderr,"Root %d/%d: q=%d\n",root+1,g.n,worst+1);
    }
    free(queue);free(component);free(seen);free(g.a);
    return 0;
}
