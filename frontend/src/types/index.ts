export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description?: string;
  owner_id: number;
  created_at: string;
  updated_at?: string;
}

export interface SKU {
  id: number;
  project_id: number;
  delivery_group_id?: number;
  name: string;
  sku_code?: string;
  length: number;
  width: number;
  height: number;
  weight: number;
  quantity: number;
  allowed_rotations: boolean[];
  fragile: boolean;
  max_stack: number;
  stacking_group?: string;
  priority: number;
  created_at: string;
}

export interface DeliveryGroup {
  id: number;
  project_id: number;
  name: string;
  color: string;
  delivery_order: number;  // 1 = first delivery (load last, near door)
  created_at: string;
}

export interface Container {
  id: number;
  project_id: number;
  name: string;
  inner_length: number;
  inner_width: number;
  inner_height: number;
  door_width: number;
  door_height: number;
  max_weight: number;
  front_axle_limit?: number;
  rear_axle_limit?: number;
  obstacles: Obstacle[];
  created_at: string;
}

export interface Obstacle {
  x: number;
  y: number;
  z: number;
  length: number;
  width: number;
  height: number;
}

export interface Placement {
  id: number;
  plan_id: number;
  sku_id: number;
  instance_index: number;
  x: number;
  y: number;
  z: number;
  rotation: number;
  length: number;
  width: number;
  height: number;
  load_order?: number;
}

export interface Plan {
  id: number;
  project_id: number;
  container_id: number;
  name: string;
  solver_mode: 'FAST' | 'IMPROVED' | 'OPTIMAL';
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';
  utilization_pct: number;
  total_weight: number;
  items_placed: number;
  items_total: number;
  weight_distribution?: {
    front_axle: number;
    rear_axle: number;
    center_of_gravity: { x: number; y: number; z: number };
  };
  is_valid: boolean;
  validation_errors: string[];
  job_id?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  placements?: Placement[];
}
