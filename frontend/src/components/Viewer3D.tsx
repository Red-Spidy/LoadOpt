import React, { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Box, Grid, Text } from '@react-three/drei';
import * as THREE from 'three';
import { Placement, SKU, Container } from '@/types';

interface BoxViewProps {
  placement: Placement;
  color: string;
}

const BoxView: React.FC<BoxViewProps> = ({ placement, color }) => {
  const meshRef = useRef<THREE.Mesh>(null);

  // Convert cm to meters for better visualization (1cm = 0.01m)
  const scale = 0.01;
  
  // Debug: log placement data for first few boxes
  if (placement.load_order !== undefined && placement.load_order < 8) {
    const posX = (placement.x + placement.length / 2) * scale;
    const posY = (placement.z + placement.height / 2) * scale;
    const posZ = (placement.y + placement.width / 2) * scale;
    const sizeX = placement.length * scale;
    const sizeY = placement.height * scale;
    const sizeZ = placement.width * scale;
    console.log(`Box ${placement.load_order}: pos=[${posX.toFixed(3)}, ${posY.toFixed(3)}, ${posZ.toFixed(3)}], size=[${sizeX.toFixed(3)}, ${sizeY.toFixed(3)}, ${sizeZ.toFixed(3)}]`);
    console.log(`  Raw: x=${placement.x}, y=${placement.y}, z=${placement.z}`);
    console.log(`  Box edge in Z: from ${(placement.y * scale).toFixed(3)} to ${((placement.y + placement.width) * scale).toFixed(3)}`);
  }
  
  // No gap - show actual positions to see if boxes are truly floating
  const visualLength = placement.length * scale;
  const visualWidth = placement.width * scale;
  const visualHeight = placement.height * scale;

  // Calculate position - box center point
  const posX = (placement.x + placement.length / 2) * scale;
  const posY = (placement.z + placement.height / 2) * scale;
  const posZ = (placement.y + placement.width / 2) * scale;

  return (
    <group position={[posX, posY, posZ]}>
      <mesh ref={meshRef}>
        <boxGeometry args={[visualLength, visualHeight, visualWidth]} />
        <meshStandardMaterial 
          color={color} 
          transparent 
          opacity={0.9}
        />
      </mesh>
      <lineSegments>
        <edgesGeometry attach="geometry" args={[new THREE.BoxGeometry(
          visualLength * 0.999,
          visualHeight * 0.999,
          visualWidth * 0.999
        )]} />
        <lineBasicMaterial attach="material" color="#333333" linewidth={1} transparent opacity={0.5} />
      </lineSegments>
    </group>
  );
};

interface ContainerViewProps {
  container: Container;
}

const ContainerView: React.FC<ContainerViewProps> = ({ container }) => {
  const scale = 0.01;

  return (
    <group position={[
      container.inner_length * scale / 2,
      container.inner_height * scale / 2,
      container.inner_width * scale / 2
    ]}>
      <lineSegments>
        <edgesGeometry attach="geometry" args={[new THREE.BoxGeometry(
          container.inner_length * scale,
          container.inner_height * scale,
          container.inner_width * scale
        )]} />
        <lineBasicMaterial attach="material" color="#333333" linewidth={2} />
      </lineSegments>
      <mesh position={[
        0,
        -container.inner_height * scale / 2,
        0
      ]}>
        <boxGeometry args={[
          container.inner_length * scale,
          0.01,
          container.inner_width * scale
        ]} />
        <meshStandardMaterial color="#e0e0e0" transparent opacity={0.5} />
      </mesh>
    </group>
  );
};

interface Viewer3DProps {
  placements: Placement[];
  skus: SKU[];
  container: Container;
}

const Viewer3D: React.FC<Viewer3DProps> = ({ placements, skus, container }) => {
  // Generate bright, light colors for each SKU
  const skuColors = React.useMemo(() => {
    const colors: Record<number, string> = {};
    const brightColors = [
      '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
      '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B88B', '#ABEBC6',
      '#FAD7A0', '#D7BDE2', '#A9DFBF', '#F9E79F', '#AED6F1',
      '#FADBD8', '#D5F4E6', '#FCF3CF', '#E8DAEF', '#EDBB99'
    ];
    skus.forEach((sku, index) => {
      colors[sku.id] = brightColors[index % brightColors.length];
    });
    return colors;
  }, [skus]);

  // Create SKU lookup
  const skuLookup = React.useMemo(() => {
    const lookup: Record<number, SKU> = {};
    skus.forEach(sku => {
      lookup[sku.id] = sku;
    });
    return lookup;
  }, [skus]);

  // Calculate container center for camera target
  const scale = 0.01;
  const containerCenter: [number, number, number] = [
    container.inner_length * scale / 2,
    container.inner_height * scale / 2,
    container.inner_width * scale / 2
  ];

  return (
    <div className="w-full h-full bg-white">
      <Canvas camera={{ position: [5, 5, 5], fov: 50 }}>
        <color attach="background" args={['#ffffff']} />
        <ambientLight intensity={0.8} />
        <pointLight position={[10, 10, 10]} intensity={0.6} />
        <pointLight position={[-10, -10, -10]} intensity={0.4} />

        <ContainerView container={container} />

        {placements.map((placement) => {
          const sku = skuLookup[placement.sku_id];
          if (!sku) return null;

          return (
            <BoxView
              key={placement.id}
              placement={placement}
              color={skuColors[sku.id]}
            />
          );
        })}

        {/* Front/Door Label */}
        <Text
          position={[
            container.inner_length * scale,
            container.inner_height * scale / 2,
            container.inner_width * scale / 2
          ]}
          rotation={[0, -Math.PI / 2, 0]}
          fontSize={0.5}
          color="#FF4444"
          anchorX="center"
          anchorY="middle"
          outlineWidth={0.02}
          outlineColor="#ffffff"
        >
          DOOR/FRONT
        </Text>

        {/* Back Label */}
        <Text
          position={[
            0,
            container.inner_height * scale / 2,
            container.inner_width * scale / 2
          ]}
          rotation={[0, Math.PI / 2, 0]}
          fontSize={0.5}
          color="#4444FF"
          anchorX="center"
          anchorY="middle"
          outlineWidth={0.02}
          outlineColor="#ffffff"
        >
          BACK
        </Text>

        <Grid
          args={[20, 20]}
          cellSize={0.5}
          cellThickness={0.5}
          cellColor="#cccccc"
          sectionSize={2}
          sectionThickness={1}
          sectionColor="#999999"
          fadeDistance={30}
          fadeStrength={1}
          followCamera={false}
          position={[
            container.inner_length * scale / 2,
            -0.01,
            container.inner_width * scale / 2
          ]}
        />

        <OrbitControls
          makeDefault
          target={containerCenter}
          enablePan={true}
          enableZoom={true}
          enableRotate={true}
          minPolarAngle={0}
          maxPolarAngle={Math.PI}
          minAzimuthAngle={-Infinity}
          maxAzimuthAngle={Infinity}
          minDistance={1}
          maxDistance={50}
          rotateSpeed={1.0}
          panSpeed={1.0}
          zoomSpeed={1.2}
        />
      </Canvas>
    </div>
  );
};

export default Viewer3D;
