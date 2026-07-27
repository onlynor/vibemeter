import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-5 text-center">
        <h2 className="fw-bold mb-3">404</h2>
        <p className="text-muted">找不到该页面。</p>
        <Link className="btn btn-primary mt-2" to="/">
          <i className="bi bi-house me-1" />回到首页
        </Link>
      </div>
    </div>
  );
}