import { useReducedMotion } from 'framer-motion';
import { motion } from 'framer-motion';
import type { RefObject, ReactNode } from 'react';

interface ChartCardProps {
  title: string;
  description: string;
  filename: string;
  svgRef: RefObject<SVGSVGElement | null>;
  children: ReactNode;
}

export default function ChartCard({ title, description, filename, svgRef, children }: ChartCardProps) {
  const reduceMotion = useReducedMotion();

  const downloadSvg = () => {
    const svg = svgRef.current;
    if (!svg) return;
    const copy = svg.cloneNode(true) as SVGSVGElement;
    copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    copy.setAttribute('width', '960');
    copy.setAttribute('height', '400');
    const content = new XMLSerializer().serializeToString(copy);
    const blob = new Blob([content], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <motion.figure
      className="chart-card"
      initial={reduceMotion ? false : { opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      aria-label={title}
    >
      <figcaption className="chart-heading">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <button type="button" className="chart-download" onClick={downloadSvg} aria-label={`Download ${title} chart as SVG`}>
          Download SVG
        </button>
      </figcaption>
      {children}
    </motion.figure>
  );
}
