import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";

const Overview = lazy(() => import("@/pages/Overview"));
const Migration = lazy(() => import("@/pages/Migration"));
const Inflation = lazy(() => import("@/pages/Inflation"));
const ElectronicCardTransactions = lazy(() => import('@/pages/ElectronicCardTransactions'));
const EconomicOutlook = lazy(() => import("@/pages/EconomicOutlook"));
const ResearchDetail = lazy(() => import("@/pages/ResearchDetail"));
const Stories = lazy(() => import("@/pages/Stories"));
const StoryPage = lazy(() => import("@/pages/Story"));
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
          <Route path="/inflation" element={<Inflation />} />
          <Route path="/electronic-card-transactions" element={<ElectronicCardTransactions />} />
          <Route path="/economic-outlook" element={<EconomicOutlook />} />
          <Route path="/economic-outlook/research/:id" element={<ResearchDetail />} />
          <Route path="/stories" element={<Stories />} />
          <Route path="/stories/:id" element={<StoryPage />} />
          <Route path="/releases/:id" element={<ReleaseAnalysis />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/health" element={<Health />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
