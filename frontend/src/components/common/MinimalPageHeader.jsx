import React from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

const MinimalPageHeader = ({ backToSection }) => {
  const navigate = useNavigate();

  const handleBack = () => {
    navigate("/", {
      state: { scrollToSection: backToSection },
    });
  };

  return (
    <header className="relative z-50 border-b border-white/10 bg-black">
      <nav className="mx-auto flex h-16 max-w-7xl items-center px-4 sm:h-20 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={handleBack}
          aria-label="Go back"
          title="Go back"
          className="mr-3 flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white/75 transition-colors hover:bg-white/10 hover:text-white"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>

        <Link
          to="/"
          id="header-brand"
          aria-label="Vehnicate home"
          className="flex items-center"
        >
          <img
            src="/hn-logo_light.png"
            alt=""
            aria-hidden="true"
            className="mr-2 h-9 sm:mr-3 sm:h-10 md:h-12"
          />
          <span
            id="header-wordmark"
            className="text-xl text-white sm:text-2xl md:text-3xl"
            style={{ fontFamily: '"Times New Roman", Times, serif' }}
          >
            vehnicate
          </span>
        </Link>
      </nav>
    </header>
  );
};

export default MinimalPageHeader;
