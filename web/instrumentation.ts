// 서버측(SSR/Route Handler/Server Action) 에러를 stdout(console.error)에 남긴다.
//
// systemd(deploy/systemd/career-log-web.service)가 이 프로세스의 stdout/stderr를
// journald로 넘기고, Fluent Bit(deploy/fluent-bit.conf.example)가 그 journald를
// Pingbell 로그 수집 API로 전달한다 - 그래서 여기서는 console.error만 하면 되고
// 별도 HTTP 호출은 필요 없다.
//
// 브라우저(클라이언트 컴포넌트)에서 나는 에러는 이 훅으로 안 잡힌다 - 서버에서 던져진
// 에러만 잡힌다. https://nextjs.org/docs/app/api-reference/file-conventions/instrumentation

type RequestErrorContext = {
  routerKind: 'Pages Router' | 'App Router'
  routePath: string
  routeType: 'render' | 'route' | 'action' | 'proxy'
  renderSource?: 'react-server-components' | 'react-server-components-payload' | 'server-rendering'
  revalidateReason: 'on-demand' | 'stale' | undefined
}

export async function onRequestError(
  error: unknown,
  request: Readonly<{ path: string; method: string; headers: Record<string, string | string[] | undefined> }>,
  context: Readonly<RequestErrorContext>,
) {
  console.error('[server-error]', {
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
    path: request.path,
    method: request.method,
    routerKind: context.routerKind,
    routePath: context.routePath,
    routeType: context.routeType,
  })
}
