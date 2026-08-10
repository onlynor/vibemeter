import { Link, NavLink, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { ResultPage } from "./pages/ResultPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RecentTasksMenu } from "./components/RecentTasksMenu";

const REPO_URL = "https://github.com/onlynor/vibemeter";

/**
 * 全站外壳：毛玻璃顶栏 + 内容 + 页脚。
 *
 * 顶栏 sticky 且半透明，内容从下方滚过时保持层次感；高度写进
 * `--header-h`，侧栏的 sticky 定位与 rail 位置都从这个变量算，
 * 改导航高度不必再去追那些散落的魔法数字。
 */
export function App() {
  return (
    <div className="app-shell d-flex flex-column min-vh-100">
      <header className="site-header">
        <div className="site-header-inner">
          <Link className="site-brand" to="/">
            <span className="site-brand-mark" aria-hidden="true" />
            <span>舆情洞察员</span>
          </Link>
          <nav className="site-nav">
            <RecentTasksMenu />
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                "site-nav-link" + (isActive ? " is-active" : "")
              }
            >
              首页
            </NavLink>
            <a
              className="site-nav-link"
              href={REPO_URL}
              target="_blank"
              rel="noopener"
              title="GitHub 仓库 onlynor/vibemeter"
            >
              <i className="bi bi-github" aria-hidden="true" />
              <span>GitHub</span>
            </a>
          </nav>
        </div>
      </header>

      <main className="flex-grow-1">
        <div className="page-container">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/result/:taskId" element={<ResultPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </main>

      <footer className="site-footer">
        <div>&copy; {new Date().getFullYear()} VibeMeter · 舆情洞察员</div>
        <div className="site-footer-links">
          <a href={REPO_URL} target="_blank" rel="noopener">
            onlynor/vibemeter
          </a>
          <span className="site-footer-sep" aria-hidden="true">·</span>
          <span>数据来自公开页面，仅供研究参考</span>
        </div>
      </footer>
    </div>
  );
}
