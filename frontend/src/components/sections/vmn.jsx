import React, { useLayoutEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

/* -------------------------------------------------------
   PAPER CARD
------------------------------------------------------- */

const MerchantCard = ({
  number,
  title,
  children,
  className = "",
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 25 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.7, ease: "easeOut" }}
      whileHover={{
        y: -6,
        rotate: -0.4,
        transition: { duration: 0.25 },
      }}
      className={`
        relative overflow-hidden
        rounded-[28px]
        bg-[#f3ead8]
        px-7 py-7
        sm:px-8 sm:py-8
        text-black
        shadow-[0_25px_60px_rgba(0,0,0,0.35)]
        ${className}
      `}
    >
      <div className="pointer-events-none absolute inset-0 opacity-[0.18]">
        <div className="absolute left-[-10%] top-[22%] h-px w-[120%] rotate-[8deg] bg-black/20" />
        <div className="absolute left-[-10%] top-[64%] h-px w-[120%] rotate-[-5deg] bg-black/15" />
        <div className="absolute left-[22%] top-[-10%] h-[120%] w-px rotate-[12deg] bg-black/10" />
      </div>

      {/* Folded corner */}
      <div
        className="
          absolute right-0 top-0
          h-0 w-0
          border-l-[42px] border-b-[42px]
          border-l-transparent
          border-b-[#ded2bc]
        "
      />

      <div className="relative z-10">
        <div className="mb-3 font-ledger text-sm font-semibold tracking-[0.18em] text-gray-500 sm:text-base">
          {number}
        </div>

        <h3 className="font-ledger text-xl font-semibold leading-tight sm:text-2xl">
          {title}
        </h3>

        <div className="mt-4 font-ledger text-sm leading-[1.65] text-gray-700 sm:text-[15px]">
          {children}
        </div>
      </div>
    </motion.div>
  );
};

/* -------------------------------------------------------
   ARROW
------------------------------------------------------- */

const FlowArrow = ({
  direction = "right",
  className = "",
}) => {
  const rotation = {
    right: "rotate-0",
    left: "rotate-180",
    down: "rotate-90",
    up: "-rotate-90",
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.7 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
      className={`
        flex items-center justify-center
        text-white/75
        ${rotation[direction]}
        ${className}
      `}
    >
      <ArrowRight
        className="h-8 w-8"
        strokeWidth={1.6}
      />
    </motion.div>
  );
};

/* -------------------------------------------------------
   TIGHT VERTICAL CONNECTOR (card 1 → card 2)
   A short, snug arrow that visually joins the two cards
   rather than floating between them. markerUnits is
   userSpaceOnUse so the arrowhead size never depends on
   the line's stroke-width (that mismatch is what was
   swallowing the arrowhead before).
------------------------------------------------------- */

const DownConnector = ({
  className = "",
  height = 100,
  idSuffix = "a",
  strokeWidth = 2,
  markerSize = 6,
  strokeOpacity = 0.85,
}) => (
  <div className={`flex justify-center ${className}`}>
    <svg
      viewBox={`0 0 20 ${height}`}
      width="20"
      height={height}
      className="overflow-visible"
    >
      <defs>
        <marker
          id={`vmnDownArrow-${idSuffix}`}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth={markerSize}
          markerHeight={markerSize}
          markerUnits="userSpaceOnUse"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 Z" fill="white" fillOpacity="0.85" />
        </marker>
      </defs>
      <motion.line
        x1="10"
        y1="2"
        x2="10"
        y2={height - 10}
        stroke="white"
        strokeOpacity={strokeOpacity}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        markerEnd={`url(#vmnDownArrow-${idSuffix})`}
        initial={{ pathLength: 0, opacity: 0 }}
        whileInView={{ pathLength: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
      />
    </svg>
  </div>
);

/* -------------------------------------------------------
   VMN
------------------------------------------------------- */

const VMN = ({ diagramOnly = false }) => {
  const flowRef = useRef(null);
  const card02Ref = useRef(null);
  const card03Ref = useRef(null);
  const card04Ref = useRef(null);
  const card05Ref = useRef(null);
  const [arrowPaths, setArrowPaths] = useState(null);

  useLayoutEffect(() => {
    const container = flowRef.current;
    const cards = [
      card02Ref.current,
      card03Ref.current,
      card04Ref.current,
      card05Ref.current,
    ];

    if (!container || cards.some((card) => !card)) return;

    const getEdgePoint = (rect, edge, containerRect) => {
      const gap = 8;
      const centerX = (rect.left + rect.right) / 2;
      const centerY = (rect.top + rect.bottom) / 2;
      let x = centerX;
      let y = centerY;

      if (edge === "right") x = rect.right + gap;
      if (edge === "left") x = rect.left - gap;
      if (edge === "top") y = rect.top - gap;
      if (edge === "bottom") y = rect.bottom + gap;

      return {
        x: ((x - containerRect.left) / containerRect.width) * 100,
        y: ((y - containerRect.top) / containerRect.height) * 100,
      };
    };

    const makePath = (start, end, startDirection, endDirection) => {
      const horizontalSpan = Math.abs(end.x - start.x);
      const verticalSpan = Math.abs(end.y - start.y);
      const handle = Math.min(
        Math.sqrt(horizontalSpan * verticalSpan) * 0.5523,
        8,
      );
      const control1 = {
        x: start.x + startDirection.x * handle,
        y: start.y + startDirection.y * handle,
      };
      const control2 = {
        x: end.x - endDirection.x * handle,
        y: end.y - endDirection.y * handle,
      };

      return `M${start.x},${start.y} C${control1.x},${control1.y} ${control2.x},${control2.y} ${end.x},${end.y}`;
    };

    const updatePaths = () => {
      const containerRect = container.getBoundingClientRect();
      if (!containerRect.width || !containerRect.height) return;

      const [card02, card03, card04, card05] = cards.map((card) =>
        card.getBoundingClientRect(),
      );

      setArrowPaths({
        card02To03: makePath(
          getEdgePoint(card02, "right", containerRect),
          getEdgePoint(card03, "top", containerRect),
          { x: 1, y: 0 },
          { x: 0, y: 1 },
        ),
        card03To04: makePath(
          getEdgePoint(card03, "bottom", containerRect),
          getEdgePoint(card04, "right", containerRect),
          { x: 0, y: 1 },
          { x: -1, y: 0 },
        ),
        card04To05: makePath(
          getEdgePoint(card04, "left", containerRect),
          getEdgePoint(card05, "bottom", containerRect),
          { x: -1, y: 0 },
          { x: 0, y: -1 },
        ),
        card05To02: makePath(
          getEdgePoint(card05, "top", containerRect),
          getEdgePoint(card02, "left", containerRect),
          { x: 0, y: -1 },
          { x: 1, y: 0 },
        ),
      });
    };

    const observer = new ResizeObserver(updatePaths);
    observer.observe(container);
    cards.forEach((card) => observer.observe(card));
    updatePaths();

    return () => observer.disconnect();
  }, []);

  return (
    <section
      id="vmn"
      className="
        relative overflow-hidden
        bg-black
        py-16
        sm:py-20
        lg:py-24
      "
    >
      {/* Ambient glow */}
      <div className="pointer-events-none absolute left-1/2 top-[20%] h-[500px] w-[700px] -translate-x-1/2 rounded-full bg-purple-600/[0.06] blur-[140px]" />

      <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* =================================================
            TITLE
        ================================================= */}

        <motion.div
          initial={{ opacity: 0, y: 25 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="mb-10 text-left sm:mb-12 lg:mb-16"
        >
          <div className="inline-block">
            <h2 className="font-ledger text-4xl font-semibold tracking-tight text-white sm:text-5xl md:text-6xl">
              {diagramOnly ? (
                <>
                  how the{" "}
                  <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent">
                    vMN
                  </span>{" "}
                  works
                </>
              ) : (
                <>
                  vehnicate Merchant Network{" "}
                  <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent">
                    (vMN)
                  </span>
                </>
              )}
            </h2>

            <div className="mt-3 flex w-full items-center">
              <div className="h-px flex-1 bg-white/40" />
              <div className="ml-1.5 h-1.5 w-1.5 rounded-full bg-white/70" />
            </div>
          </div>

          {!diagramOnly && (
            <div className="mt-8 max-w-5xl space-y-5 font-ledger text-base leading-relaxed text-gray-300 sm:text-lg lg:text-xl">
              <p>
                The vMN is the "channel" that is used to channel economic
                benefit to you.
              </p>

              <p>
                In short, it is a{" "}
                <span className="underline underline-offset-4">
                  network of merchants
                </span>{" "}
                who deeply trust the vision of zero-accidents and{" "}
                <span className="underline underline-offset-4">
                  accept Ellars in exchange for a product or service
                </span>.
              </p>

              <p>
                At present, we have one merchant: grocery shop
                {" "}
                <strong className="font-semibold text-white">
                  Muthaaramman Mini Supermarket
                </strong>
                , where users can avail a discount on their purchase in
                exchange for Ellars.
              </p>

              <p className="pt-4">
                As more users and merchants join the ecosystem, the value of
                Ellar will rise and the merchant's business will become more
                attractive to customers, helping them bring in more customers
                with less ad spend.
              </p>

              <p className="pt-3 text-gray-400">
                Visit the{" "}
                <Link
                  to="/vmn"
                  className="
                    text-purple-400
                    underline
                    decoration-purple-400/50
                    underline-offset-4
                    hover:text-pink-400
                    transition-colors
                    duration-300
                  "
                >
                  vMN page
                </Link>{" "}
                to know more.
              </p>
            </div>
          )}
        </motion.div>

        {diagramOnly && (
          <>

        {/* =================================================
            STEP 01
        ================================================= */}

        <div className="mx-auto mt-14 max-w-md">
          <MerchantCard
            number="01"
            title="You drive & earn Ellars"
          >
            Accumulate Ellars as you go over road-defects.
          </MerchantCard>
        </div>

        {/* Arrow: 01 → 02 (desktop only — mobile has its own copy below).
            Height brought way down so card 02 sits close beneath card 01
            instead of floating in a big gap. */}
        <DownConnector
          className="hidden lg:flex mt-1"
          height={70}
          idSuffix="desktop"
          strokeWidth={2.25}
          markerSize={14.4}
          strokeOpacity={0.75}
        />

        {/* =================================================
          DESKTOP FLOW — four separate corner-to-corner arrows.
          Cycle: 02 → 03 → 04 → 05 → 02.
        ================================================= */}

        <div
          ref={flowRef}
          className="
            relative mx-auto mt-0
            hidden
            w-full
            max-w-[900px]
            aspect-square
            lg:block
          "
        >
          <svg
            viewBox="0 0 100 100"
            className="
              pointer-events-none
              absolute inset-0
              z-0
              h-full w-full
              overflow-visible
            "
          >
            <defs>
              <marker
                id="vmnFlowArrow"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="1.6"
                markerHeight="1.6"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path d="M0,0 L10,5 L0,10 Z" fill="white" fillOpacity="1" />
              </marker>
            </defs>

            {/* 02 → 03 */}
            <path
              d={arrowPaths?.card02To03}
              fill="none"
              stroke="white"
              strokeOpacity="0.75"
              strokeWidth="0.25"
              strokeLinecap="round"
              markerEnd="url(#vmnFlowArrow)"
            />

            {/* 03 → 04 */}
            <path
              d={arrowPaths?.card03To04}
              fill="none"
              stroke="white"
              strokeOpacity="0.75"
              strokeWidth="0.25"
              strokeLinecap="round"
              markerEnd="url(#vmnFlowArrow)"
            />

            {/* 04 → 05 */}
            <path
              d={arrowPaths?.card04To05}
              fill="none"
              stroke="white"
              strokeOpacity="0.75"
              strokeWidth="0.25"
              strokeLinecap="round"
              markerEnd="url(#vmnFlowArrow)"
            />

            {/* 05 → 02 */}
            <path
              d={arrowPaths?.card05To02}
              fill="none"
              stroke="white"
              strokeOpacity="0.75"
              strokeWidth="0.25"
              strokeLinecap="round"
              markerEnd="url(#vmnFlowArrow)"
            />
          </svg>

          <div
            className="
              absolute left-1/2 top-1/2 z-10
              w-[280px] max-w-[34%]
              -translate-x-1/2 -translate-y-1/2
              rounded-[2rem] border border-white/30
              bg-black/80 px-5 py-4
              font-ledger text-xs leading-relaxed text-white/80
              shadow-[0_12px_32px_rgba(0,0,0,0.35)]
              sm:text-sm
            "
          >
            <ul className="list-disc space-y-2 pl-4 marker:text-white/55">
              <li>New customers walk into the merchant&apos;s store</li>
              <li>Better merchant-customer relationships</li>
              <li>Reduced Ad spend</li>
            </ul>
          </div>

          {/* CARD 02 — top vertex (50, 15) */}
          <div
            ref={card02Ref}
            className="
              absolute
              w-[300px]
              -translate-x-1/2 -translate-y-1/2
              z-10
            "
            style={{ left: "50%", top: "15%" }}
          >
            <MerchantCard number="02" title="Go to a merchant">
              Visit a grocer in the vMN and redeem your Ellars
              for a discount on your purchase.
            </MerchantCard>
          </div>

          {/* CARD 03 — right vertex (82, 50) */}
          <div
            ref={card03Ref}
            className="
              absolute
              w-[300px]
              -translate-x-1/4 -translate-y-1/2
              z-10
            "
            style={{ left: "90%", top: "50%" }}
          >
            <MerchantCard number="03" title="Ellar balance updates">
              Your Ellar balance reduces.
              Merchant's balance increases.
              You walk out with a discount.
            </MerchantCard>
          </div>

          {/* CARD 04 — bottom vertex (50, 85) */}
          <div
            ref={card04Ref}
            className="
              absolute
              w-[400px]
              -translate-x-1/2 -translate-y-1/2
              z-10
            "
            style={{ left: "50%", top: "85%" }}
          >
            <MerchantCard number="04" title="The grocer rewards customers">
              <>
                <p>The grocer uses accumulated Ellars to:</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  <li>Pull in new customers</li>
                  <li>Encourage existing ones to return like a loyalty program.</li>
                </ul>
              </>
            </MerchantCard>
          </div>

          {/* CARD 05 — left vertex (18, 50) */}
          <div
            ref={card05Ref}
            className="
              absolute
              w-[300px]
              -translate-x-3/4 -translate-y-1/2
              z-10
            "
            style={{ left: "10%", top: "50%" }}
          >
            <MerchantCard number="05" title="Ellars go from grocer to user">
              The user receives Ellars from the grocer.
            </MerchantCard>
          </div>
        </div>

        {/* =================================================
            MOBILE FLOW
        ================================================= */}

        <div className="mt-16 lg:hidden">

          {/* Arrow: 01 → 02 */}
          <DownConnector className="mt-1 mb-1" height={70} idSuffix="mobile" />

          {/* 02 */}
          <MerchantCard
            number="02"
            title="Go to a merchant"
          >
            Visit a grocer in the vMN and redeem your Ellars
            for a discount on your purchase.
          </MerchantCard>

          <div className="flex justify-center py-4">
            <FlowArrow direction="down" />
          </div>

          {/* 03 */}
          <MerchantCard
            number="03"
            title="Your Ellar balance changes"
          >
            Your Ellar balance decreases by the amount you spend,
            while the merchant's Ellar balance increases.
          </MerchantCard>

          <div className="flex justify-center py-4">
            <FlowArrow direction="down" />
          </div>

          {/* 04 */}
          <MerchantCard
            number="04"
            title="The grocer rewards customers"
          >
            The grocer can use accumulated Ellars to reward
            customers and encourage them to return.
          </MerchantCard>

          <div className="flex justify-center py-4">
            <FlowArrow direction="down" />
          </div>

          {/* 05 */}
          <MerchantCard
            number="05"
            title="Ellars go from grocer to user"
          >
            The user receives Ellars from the grocer, increasing
            their Ellar balance once again.
          </MerchantCard>

          {/* Mobile explanation */}
          <motion.div
            initial={{
              opacity: 0,
              y: 20,
            }}
            whileInView={{
              opacity: 1,
              y: 0,
            }}
            viewport={{
              once: true,
            }}
            transition={{
              duration: 0.7,
            }}
            className="
              mx-auto
              max-w-md
              py-12
              text-center
            "
          >
            <p className="font-ledger text-sm leading-[1.7] text-white/65">
              Customers prefer this grocer over his competitors
              because he accepts Ellars. This helps the grocer
              drive more foot fall and build customer
              relationships without having to pour money into ads.
            </p>

            <p className="mt-5 font-ledger text-sm font-medium leading-[1.7] text-white/85">
              Therefore, the merchant has acquired both customers
              and Ellars.
            </p>

            <div className="mt-8 flex flex-col items-center gap-2">
              <FlowArrow direction="up" />
              <span className="font-ledger text-xs text-white/45">
                back to card 02 — the cycle continues
              </span>
            </div>
          </motion.div>
        </div>

          </>
        )}

      </div>
    </section>
  );
};

export default VMN;