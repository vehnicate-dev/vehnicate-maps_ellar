import React from "react";
import MinimalPageHeader from "../components/common/MinimalPageHeader";
import VMN from "../components/sections/vmn";

const VmnPage = () => (
  <div className="min-h-screen bg-black text-white">
    <MinimalPageHeader backToSection="vmn" />
    <main>
      <VMN diagramOnly />
    </main>
  </div>
);

export default VmnPage;
