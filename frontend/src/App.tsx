import Hero from "./components/Hero";
import TissueSimulation from "./components/TissueSimulation";
import Leaderboard from "./components/Leaderboard";
import ScenarioBrowser from "./components/ScenarioBrowser";
import ScoreBreakdown from "./components/ScoreBreakdown";
import ErrorAnalysis from "./components/ErrorAnalysis";
import ClassDistribution from "./components/ClassDistribution";
import PerLabelMetrics from "./components/PerLabelMetrics";

export default function App() {
  return (
    <div className="min-h-screen bg-black text-zinc-100">
      <main className="max-w-6xl mx-auto px-6 py-12">
        <Hero />
        <TissueSimulation />
        <Leaderboard />
        <ScenarioBrowser />
        <ScoreBreakdown />
        <ErrorAnalysis />
        <ClassDistribution />
        <PerLabelMetrics />

        <footer className="border-t border-zinc-800 pt-6 mt-12 text-xs text-zinc-500">
          <div>Calibrated on GSE40279 (656 samples) and GSE51057 (329 multi-tissue samples) from NCBI GEO</div>
          <div>Built for Caltech Longevity Hackathon 2026</div>
          <div className="text-rose-400 mt-1">Research tool — not for clinical use</div>
        </footer>
      </main>
    </div>
  );
}
