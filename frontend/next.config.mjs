/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // 本机（Windows）沙箱禁止创建带 IPC 具名管道的子进程，Next 默认的
    // child_process.fork worker 会抛 `spawn EPERM`，构建直接失败。
    //   workerThreads: 静态生成 worker 改用 worker_threads（不走具名管道）
    //   webpackBuildWorker: false: webpack 编译回主进程——该 worker 不读
    //     workerThreads 开关，只能整体关掉
    // 代价是构建并行度下降（本项目规模无感）。详见 docs/mistakes.md。
    workerThreads: true,
    webpackBuildWorker: false,
  },
};

export default nextConfig;
