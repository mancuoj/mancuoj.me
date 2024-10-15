export function Home() {
  return (
    <div className="font-sans antialiased">
      <div className="flex min-h-dvh flex-col items-center justify-center gap-5">
        <h1 className="font-serif text-3xl font-bold">Hi, I'm mancuoj</h1>
        <div className="flex items-center gap-2 text-2xl">
          <a href="https://github.com/mancuoj" className="i-lucide-github" />
          <a href="https://x.com/humancuoj" className="i-lucide-twitter" />
          <a href="https://blog.mancuoj.me" className="i-lucide-smile" />
        </div>
      </div>
    </div>
  )
}
