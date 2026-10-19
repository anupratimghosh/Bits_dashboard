import { NavLink, Route, Routes } from 'react-router-dom'
import { ThemeToggle } from './components/UI'
import { useApi } from './useData'
import Campuses from './pages/Campuses'
import Departments from './pages/Departments'
import FacultyDetail from './pages/FacultyDetail'
import FacultyList from './pages/FacultyList'
import Overview from './pages/Overview'
import PublicationDetail from './pages/PublicationDetail'
import Publications from './pages/Publications'
import Review from './pages/Review'
import Upload from './pages/Upload'

function Nav() {
  const { data: stats } = useApi('/admin/stats')
  const queue = stats?.open_queue || 0
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">BITS Research Analytics</div>
      </div>

      <nav className="nav" aria-label="Main">
        <NavLink to="/" end>Executive summary</NavLink>
        <NavLink to="/campuses">Campuses</NavLink>
        <NavLink to="/departments">Departments</NavLink>
        <NavLink to="/faculty">Faculty</NavLink>
        <NavLink to="/publications">Publications</NavLink>

        <span className="nav-sep" aria-hidden="true" />
        <NavLink to="/upload">Upload</NavLink>
        <NavLink to="/review">
          Attribution review
          {queue > 0 && <span className="nav-badge">{queue}</span>}
        </NavLink>
      </nav>

      <ThemeToggle />
    </header>
  )
}

export default function App() {
  return (
    <div className="shell">
      <Nav />
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/campuses" element={<Campuses />} />
          <Route path="/departments" element={<Departments />} />
          <Route path="/faculty" element={<FacultyList />} />
          <Route path="/faculty/:id" element={<FacultyDetail />} />
          <Route path="/publications" element={<Publications />} />
          <Route path="/publications/:id" element={<PublicationDetail />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/review" element={<Review />} />
          <Route path="*" element={<div className="empty">Page not found</div>} />
        </Routes>
      </main>
    </div>
  )
}
