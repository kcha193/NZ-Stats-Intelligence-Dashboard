import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";

const Overview = lazy(() => import("@/pages/Overview"));
const Migration = lazy(() => import("@/pages/Migration"));
const ReleaseAnalysis = lazy(() => import("@/pages/ReleaseAnalysis"));
const Calendar = lazy(() => import("@/pages/Calendar"));
const Health = lazy(() => import("@/pages/Health"));

function NotFound() {
  return <p className="text-sm">That page does not exist. Use the navigation above.</p>;
}

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/migration" element={<Migration />} />
          <Route path="/releases/:id" element={<ReleaseAnalysis />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/health" element={<Health />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
