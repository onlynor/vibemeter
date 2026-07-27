import { Link, NavLink, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { ResultPage } from "./pages/ResultPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RecentTasksMenu } from "./components/RecentTasksMenu";

/** 顶部导航 + 页脚的全站壳。最近任务作为全局下拉菜单放在导航最上方。 */
export function App() {
  return (
    <div className="app-shell d-flex flex-column min-vh-100">
      <nav className="navbar navbar-dark app-navbar shadow-sm">
        <div className="container app-navbar-container">
          <Link className="navbar-brand fw-bold d-flex align-items-center link-reset" to="/">
            <span className="brand-dot" />
            <span className="ms-2">舆情洞察员</span>
          </Link>
          <div className="d-flex align-items-center gap-3">
            <RecentTasksMenu />
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                "navbar-text small link-reset " + (isActive ? "text-white" : "text-light")
              }
            >
              首页
            </NavLink>
            <a
              className="navbar-text text-light small d-inline-flex align-items-center link-reset"
              href="https://github.com/onlynor/vibemeter"
              target="_blank"
              rel="noopener"
              title="GitHub 仓库 onlynor/vibemeter"
            >
              <i className="bi bi-github me-1" />
              <span>VibeMeter</span>
            </a>
          </div>
        </div>
      </nav>

      <main className="flex-grow-1">
        <div className="page-container">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/result/:taskId" element={<ResultPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </main>

      <footer className="text-center app-footer small py-4">
        <div>&copy; {new Date().getFullYear()} Sentiment Insight Platform</div>
        <div className="mt-1">
          <a
            className="link-reset d-inline-flex align-items-center text-muted"
            href="https://github.com/onlynor/vibemeter"
            target="_blank"
            rel="noopener"
          >
            <i className="bi bi-github me-1" />onlynor/vibemeter
          </a>
        </div>
      </footer>
    </div>
  );
}