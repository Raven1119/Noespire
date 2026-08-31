import { Route, Routes } from "react-router-dom";
import { Home } from "./screens/Home";
import { WorkspaceShell } from "./screens/WorkspaceShell";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/problems/:problemId" element={<WorkspaceShell />} />
    </Routes>
  );
}
