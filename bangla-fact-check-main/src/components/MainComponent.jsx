import Navbar from "./Navbar";
import Footer from "./Footer";

export default function MainComponent({ children }) {
  return (
    <div className="min-h-screen flex flex-col bg-background-light dark:bg-background-dark">
      <Navbar />
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
      <Footer />
    </div>
  );
}
