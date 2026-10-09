import { motion, useAnimationFrame, useMotionValue, useReducedMotion, useTransform } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';

type OrbitPlanetProps = {
  radiusX: number;
  radiusY: number;
  duration: number;
  size: number;
  color: string;
  glow: string;
  offset: number;
  paused: boolean;
};

function OrbitPlanet({ radiusX, radiusY, duration, size, color, glow, offset, paused }: OrbitPlanetProps) {
  const reducedMotion = useReducedMotion();
  const angle = useMotionValue(offset);

  useAnimationFrame((time) => {
    if (reducedMotion || paused) {
      return;
    }

    const seconds = time / 1000;
    angle.set(offset + (seconds / duration) * Math.PI * 2);
  });

  const x = useTransform(angle, (value) => Math.cos(value) * radiusX);
  const y = useTransform(angle, (value) => Math.sin(value) * radiusY);

  return (
    <motion.div
      className="solar-planet"
      style={{
        width: size,
        height: size,
        background: color,
        boxShadow: `0 0 ${Math.max(size * 1.5, 18)}px ${glow}`,
        x,
        y,
      }}
    />
  );
}

export default function SolarSystem() {
  const reducedMotion = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const [sceneOnly, setSceneOnly] = useState(false);
  const visiblePaused = reducedMotion || paused;

  useEffect(() => {
    document.body.classList.toggle('scene-only', sceneOnly);
    return () => document.body.classList.remove('scene-only');
  }, [sceneOnly]);

  const stars = useMemo(
    () =>
      Array.from({ length: 110 }, (_, index) => ({
        id: index,
        left: `${(index * 17) % 100}%`,
        top: `${(index * 29) % 100}%`,
        size: 2 + ((index * 7) % 3),
        opacity: 0.45 + ((index * 13) % 50) / 100,
      })),
    [],
  );

  const planets = [
    { radiusX: 128, radiusY: 64, duration: 12, size: 18, color: '#f9c74f', glow: 'rgba(249, 199, 79, 0.8)', offset: 0.4 },
    { radiusX: 196, radiusY: 88, duration: 16, size: 24, color: '#7dd3fc', glow: 'rgba(125, 211, 252, 0.8)', offset: 2.1 },
    { radiusX: 262, radiusY: 120, duration: 22, size: 28, color: '#c084fc', glow: 'rgba(192, 132, 252, 0.8)', offset: 4.2 },
    { radiusX: 326, radiusY: 154, duration: 28, size: 34, color: '#f472b6', glow: 'rgba(244, 114, 182, 0.8)', offset: 1.7 },
  ];

  return (
    <div className="solar-system" aria-hidden="true">
      <button type="button" className="scene-toggle" onClick={() => setSceneOnly((v) => !v)} aria-pressed={sceneOnly}>
        {sceneOnly ? 'Show panels' : 'Show scene'}
      </button>
      <button type="button" className="motion-toggle" onClick={() => setPaused((current) => !current)}>
        {visiblePaused ? 'Resume motion' : 'Pause motion'}
      </button>

      <div className="solar-sun" />

      {stars.map((star) => (
        <span
          key={star.id}
          className="solar-star"
          style={{
            left: star.left,
            top: star.top,
            width: star.size,
            height: star.size,
            opacity: star.opacity,
          }}
        />
      ))}

      {planets.map((planet, index) => (
        <OrbitPlanet
          key={index}
          radiusX={planet.radiusX}
          radiusY={planet.radiusY}
          duration={planet.duration}
          size={planet.size}
          color={planet.color}
          glow={planet.glow}
          offset={planet.offset}
          paused={visiblePaused}
        />
      ))}

      <div className="solar-ring solar-ring-1" />
      <div className="solar-ring solar-ring-2" />
      <div className="solar-ring solar-ring-3" />
    </div>
  );
}
