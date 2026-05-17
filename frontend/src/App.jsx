import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import RunDetail from './pages/RunDetail'

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/runs/:id" element={<RunDetail />} />
      </Routes>
    </BrowserRouter>
  )
}
