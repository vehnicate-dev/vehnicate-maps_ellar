import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import MinimalPageHeader from "../components/common/MinimalPageHeader";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";
const ELLAR_TOTALS_URL =
  "https://vehnicate-mapsellar-production.up.railway.app/public/ellar-totals";

const Formula = ({ children }) => (
  <div className="my-6 overflow-x-auto rounded border border-white/10 bg-white/[0.03] px-4 py-5 text-center font-ledger text-lg text-white sm:text-xl">
    {children}
  </div>
);

const Ellar = () => {
  const [ellarTotals, setEllarTotals] = useState(null);

  useEffect(() => {
    let isActive = true;

    const fetchEllarTotals = async () => {
      try {
        const response = await fetch(ELLAR_TOTALS_URL);
        if (!response.ok) throw new Error(`Request failed: ${response.status}`);

        const totals = await response.json();
        if (isActive) setEllarTotals(totals);
      } catch (error) {
        if (isActive) console.error("[ellar-totals] request failed:", error);
      }
    };

    fetchEllarTotals();
    const interval = window.setInterval(fetchEllarTotals, 60_000);

    return () => {
      isActive = false;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen bg-black text-white">
      <MinimalPageHeader backToSection="ellar" />
      <section
        className="relative overflow-hidden bg-gradient-to-b from-black via-purple-900/5 to-black py-12 sm:py-16 md:py-20"
      >
        <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <section
            aria-label="Total Ellars issued"
            aria-live="polite"
            className="mb-12 border-y border-white/15 py-5 text-center sm:mb-16"
          >
            <p className="font-ledger text-sm font-semibold text-white sm:text-base">
              total Ellars issued so far:
            </p>
            <div className="mt-3 flex flex-col items-center justify-center gap-2 font-ledger text-base text-gray-300 sm:flex-row sm:gap-8 sm:text-lg">
              <p>
                <span className="mr-2 font-semibold text-white">
                  {ellarTotals
                    ? Number(ellarTotals.frozen_ellar || 0).toFixed(2)
                    : "--.--"}
                </span>
                Frozen Ellars
              </p>
              <span aria-hidden="true" className="hidden text-white/50 sm:inline">
                |
              </span>
              <p>
                <span className="mr-2 font-semibold text-white">
                  {ellarTotals
                    ? Number(ellarTotals.liquid_ellar || 0).toFixed(2)
                    : "--.--"}
                </span>
                Liquid Ellars
              </p>
            </div>
          </section>

          <motion.header
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="mx-auto mb-16 max-w-5xl text-center sm:mb-20"
          >
            <h1 className="font-ledger text-3xl font-semibold leading-tight text-white sm:text-4xl md:text-5xl">
              The <span className={gradientText}>Ellar</span> - history, working
              &amp; the future
            </h1>
            <div className="mx-auto mt-5 flex max-w-3xl items-center">
              <div className="h-px flex-1 bg-white/30" />
              <div className="mx-2 h-1.5 w-1.5 rounded-full bg-pink-400" />
              <div className="h-px flex-1 bg-white/30" />
            </div>
          </motion.header>

          <section aria-labelledby="story-heading" className="mb-24 sm:mb-28">
            <h2 id="story-heading" className="mb-7 font-ledger text-2xl font-bold text-white underline decoration-white/40 underline-offset-8 sm:text-3xl">
              Story behind the name
            </h2>
            <div className="grid items-stretch gap-8 lg:grid-cols-2 lg:gap-12">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 0.1 }}
                className="flex flex-col justify-center space-y-5 font-ledger text-base leading-relaxed text-gray-300 sm:text-lg lg:text-xl"
              >
                <p>
                  Legend has it that a Chola prince once ran over a calf with
                  his chariot. When the cow pleaded for justice, the king
                  executed his own son the same way, earning the title{" "}
                  <span className={`${gradientText} font-semibold`}>Manu Needhi Cholan</span>.
                </p>
                <p>
                  In a time when we encounter cases such as the Pune Porsche
                  incident, this story of the Chola king inspired vehnicate.
                  The Ellar honours the king, whose original name was{" "}
                  <span className={`${gradientText} font-semibold`}>Ellalan</span>.
                </p>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="relative flex items-center justify-center"
              >
                <div
                  aria-hidden="true"
                  className="absolute -inset-10 bg-[radial-gradient(ellipse_at_center,rgba(168,85,247,0.3)_0%,rgba(236,72,153,0.16)_42%,transparent_72%)] blur-2xl"
                />
                <div className="relative z-10 w-full max-w-[14.5rem] overflow-hidden rounded-lg border border-white/20 shadow-[0_0_24px_rgba(168,85,247,0.18)]">
                  <img
                    src="/Ellalan.jpg"
                    alt="King Ellalan"
                    className="block h-auto w-full"
                    onError={(event) => {
                      event.currentTarget.onerror = null;
                      event.currentTarget.src =
                        "https://placehold.co/500x686/000000/FFFFFF?text=Ellalan";
                    }}
                  />
                </div>
              </motion.div>
            </div>
          </section>

          <section aria-labelledby="working-heading" className="mb-24 sm:mb-28">
            <h2 id="working-heading" className="mb-8 font-ledger text-2xl font-bold text-white underline decoration-white/40 underline-offset-8 sm:text-3xl">
              The working
            </h2>
            <div className="space-y-10 font-ledger text-base leading-relaxed text-gray-300 sm:text-lg">
              <p>
                Ellars are issued through road observations, then released
                according to how those observations are verified. The
                rules below describe the lifecycle of a detection, from its
                first report to its eventual confirmation or review.
              </p>

              <article>
                <h3 className="mb-3 text-lg font-semibold text-white sm:text-xl">
                  1. Set the trip multiplier
                </h3>
                <p>
                  Each trip is assigned a multiplier based on the mode the user
                  chooses. If the user has a phone mount and uses the phone&apos;s
                  camera to help us map the roads, the multiplier is 1;
                  otherwise, it is 0.5. That is to say, if you use a phone
                  mount, you can double your Ellar earnings. The same trip
                  multiplier is used for both discovery and confirmation
                  rewards.
                </p>
                <Formula>
                  <div className="whitespace-nowrap">
                    m = 1.0 (phone on mount &amp; camera ON trip)
                  </div>
                  <div className="whitespace-nowrap">
                    m = 0.5 (camera OFF trip)
                  </div>
                </Formula>
              </article>

              <article>
                <h3 className="mb-3 text-lg font-semibold text-white sm:text-xl">
                  2. Discovery reward - frozen Ellar
                </h3>
                <p>
                  If a user who is the <em>N</em>
                  <sup>th</sup> user to drive across a hexagon is the first
                  person to encounter a road defect, they are its discoverer
                  and receive the following discovery reward in frozen Ellars.
                </p>
                <p>
                  <span className="font-semibold text-white">Note:</span>{" "}
                  Detections within 15 metres of another detection are treated
                  as the same observation, not a new discovery.
                </p>
                <Formula>
                  R<sub>discovery</sub> = m(4 - 2 log<sub>10</sub>N) Frozen
                  Ellars, for N ≤ 100
                </Formula>
                <p>
                  After the first 100 travellers of that hexagon, subsequent
                  users receive the average amount of frozen Ellars issued
                  from that hexagon per road defect in that hexagon as their
                  discovery reward.
                </p>
                <Formula>
                  R<sub>discovery</sub> = m × E<sub>hex</sub> / r<sub>D</sub>{" "}
                  Frozen Ellars, for N &gt; 100
                </Formula>
                <p>
                  Here <em>E</em><sub>hex</sub> is the total frozen Ellars
                  issued for that hexagon and <em>r</em><sub>D</sub> is its
                  number of unique road defects.
                </p>
              </article>

              <article>
                <h3 className="mb-3 text-lg font-semibold text-white sm:text-xl">
                  3. Reward eligible confirmations
                </h3>
                <p>
                  A repeat observation can confirm an existing defect. A user
                  earns this reward only if they are not its discoverer and
                  have not already been paid for confirming it. Repeated
                  encounters by one person count once: <em>n</em><sub>D</sub>{" "}
                  is the number of unique previous users who flagged that
                  defect, plus 1. Confirmation rewards go
                  directly to the user&apos;s liquid balance.
                </p>
                <Formula>
                  R<sub>confirmation</sub> = m(2 - log<sub>10</sub>n<sub>D</sub>) Liquid Ellars
                </Formula>
              </article>

              <article>
                <h3 className="mb-3 text-lg font-semibold text-white sm:text-xl">
                  4. Release the discoverer&apos;s frozen reward
                </h3>
                <p>
                  When an unverified defect is confirmed by another user, it is
                  marked legitimate. The Frozen Ellars discovery reward that was given to that road-defect&apos;s discoverer
                  is then moved into their liquid balance.
                  The release uses the discoverer&apos;s original trip
                  multiplier and their position in the hexagon&apos;s travel
                  history.
                </p>
                <p>
                  <span className="font-semibold text-white">Note:</span>{" "}
                  A discoverer can confirm their own observation, but
                  does not earn a confirmation reward for it.
                </p>
                <Formula>
                  <div className="whitespace-nowrap">
                    FrozenEllar_Balance<sub>discoverer</sub>{" "}
                    <span className="mx-1 text-2xl font-bold text-pink-300 sm:text-3xl">-=</span>{" "}
                    R<sub>discovery</sub> received for that road-defect
                  </div>
                  <div className="whitespace-nowrap">
                    Liquid<sub>discoverer</sub>{" "}
                    <span className="mx-1 text-2xl font-bold text-pink-300 sm:text-3xl">+=</span>{" "}
                    R<sub>discovery</sub>
                  </div>
                </Formula>
              </article>

              <article>
                <h3 className="mb-3 text-lg font-semibold text-white sm:text-xl">
                  5. Review unresolved discoveries
                </h3>
                <p>
                  At the rulebook&apos;s ten-trip review point, defects first
                  reported in the corresponding earlier trip are checked. If
                  a defect is neither confirmed nor at least 30% confidence,
                  it is removed. The discoverer&apos;s frozen discovery amount
                  is forfeited, and 1% of that amount is also deducted from
                  their liquid balance.
                </p>
                <Formula>
                  <div className="whitespace-nowrap">
                    Frozen<sub>discoverer</sub>{" "}
                    <span className="mx-1 text-2xl font-bold text-pink-300 sm:text-3xl">-=</span>{" "}
                    R<sub>discovery</sub>
                  </div>
                  <div className="whitespace-nowrap">
                    Liquid<sub>discoverer</sub>{" "}
                    <span className="mx-1 text-2xl font-bold text-pink-300 sm:text-3xl">-=</span>{" "}
                    0.01 × R<sub>discovery</sub>
                  </div>
                </Formula>
              </article>
            </div>
          </section>

          <section aria-labelledby="future-heading" className="max-w-5xl">
            <h2 id="future-heading" className="mb-5 font-ledger text-2xl font-bold text-white underline decoration-white/40 underline-offset-8 sm:text-3xl">
              The Future
            </h2>
            <div className="space-y-6 font-ledger text-base leading-relaxed text-gray-300 sm:text-lg">
              <p>
                Rewarding every pothole driven over is the supply era of
                Ellars. At first, as more people travel more roads, discovery
                rewards bring new Ellars into circulation. Once enough users
                have covered most roads, fewer new discoveries remain and the
                rate of new Ellar creation slows.
              </p>

              <div className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.03] p-3 sm:p-6">
                <svg
                  viewBox="0 0 800 360"
                  role="img"
                  aria-labelledby="supply-chart-title supply-chart-description"
                  className="h-auto w-full"
                >
                  <title id="supply-chart-title">Illustrative Ellar supply over time</title>
                  <desc id="supply-chart-description">
                    Supply begins slowly, rises rapidly as road coverage grows,
                    then levels off as most roads have been covered.
                  </desc>
                  <defs>
                    <linearGradient id="ellar-curve" x1="0" x2="1" y1="0" y2="0">
                      <stop offset="0%" stopColor="#a78bfa" />
                      <stop offset="100%" stopColor="#ec4899" />
                    </linearGradient>
                  </defs>
                  <g stroke="rgba(255,255,255,0.12)" strokeWidth="1">
                    <line x1="72" y1="42" x2="72" y2="300" />
                    <line x1="72" y1="300" x2="750" y2="300" />
                    <line x1="72" y1="214" x2="750" y2="214" strokeDasharray="4 8" />
                    <line x1="72" y1="128" x2="750" y2="128" strokeDasharray="4 8" />
                    <line x1="72" y1="42" x2="750" y2="42" strokeDasharray="4 8" />
                  </g>
                  <path
                    d="M 78 294 C 185 292, 225 284, 275 255 C 332 221, 345 157, 416 112 C 478 73, 552 56, 625 52 C 675 49, 715 49, 744 49"
                    fill="none"
                    stroke="url(#ellar-curve)"
                    strokeLinecap="round"
                    strokeWidth="7"
                  />
                  <g fill="rgba(255,255,255,0.72)" fontFamily="Ledger, serif" fontSize="15">
                    <text x="78" y="326">Time</text>
                    <text transform="translate(25 225) rotate(-90)">Cumulative supply of Ellars</text>
                    <text x="94" y="278" fill="rgba(255,255,255,0.48)" fontSize="12">Early discovery</text>
                    <text x="350" y="185" fill="rgba(255,255,255,0.48)" fontSize="12">Growing road coverage</text>
                    <text x="605" y="75" fill="rgba(255,255,255,0.48)" fontSize="12">Mature coverage</text>
                  </g>
                </svg>
              </div>
              <p className="text-sm text-gray-400">
                Conceptual supply curve: slow initial growth, a rapid expansion
                phase, then a flattening as road coverage matures.
              </p>

              <p>
                As supply growth approaches that flatter phase, vehnicate plans
                to launch a <span className={`${gradientText} font-semibold`}>game</span>{" "}
                that rewards good driving rather than potholes encountered.
                Maintaining your lane earns Ellars; cutting lanes costs Ellars.
              </p>
              <p>
                Because Ellars can have real utility through the{" "}
                <a
                  href="https://vehnicate.com/vmn"
                  className="font-semibold text-white underline decoration-pink-400 underline-offset-4 transition-colors hover:text-pink-300"
                >
                  vMN
                </a>
                , being a good driver can become a genuinely profitable choice.
              </p>
            </div>
          </section>
        </div>
      </section>
    </div>
  );
};

export default Ellar;