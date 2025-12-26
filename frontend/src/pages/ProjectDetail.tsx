import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsAPI, skusAPI, containersAPI, plansAPI, deliveryGroupsAPI } from '@/services/api';
import { ArrowLeft, Upload, Plus, Play, Trash2, Edit2, Tag, Package } from 'lucide-react';
import type { DeliveryGroup, SKU } from '@/types';

const ProjectDetail: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'skus' | 'groups' | 'containers' | 'plans'>('skus');
  
  // Modal states
  const [showContainerModal, setShowContainerModal] = useState(false);
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [showSKUModal, setShowSKUModal] = useState(false);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [editingGroup, setEditingGroup] = useState<DeliveryGroup | null>(null);
  const [editingSKU, setEditingSKU] = useState<SKU | null>(null);
  
  // Form states
  const [containerForm, setContainerForm] = useState({
    name: '',
    inner_length: '',
    inner_width: '',
    inner_height: '',
    door_width: '',
    door_height: '',
    max_weight: '',
    front_axle_limit: '',
    rear_axle_limit: '',
  });
  const [planForm, setPlanForm] = useState({
    name: '',
    container_id: '',
  });
  const [skuForm, setSkuForm] = useState({
    name: '',
    length: '',
    width: '',
    height: '',
    weight: '',
    quantity: '1',
    fragile: false,
    max_stack: '999',
    delivery_group_id: '',
  });
  const [groupForm, setGroupForm] = useState({
    name: '',
    color: '#3B82F6',
    delivery_order: '1',
  });

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsAPI.get(Number(projectId)),
  });

  const { data: skus } = useQuery({
    queryKey: ['skus', projectId],
    queryFn: () => skusAPI.list(Number(projectId)),
  });

  const { data: containers } = useQuery({
    queryKey: ['containers', projectId],
    queryFn: () => containersAPI.list(Number(projectId)),
  });

  const { data: plans } = useQuery({
    queryKey: ['plans', projectId],
    queryFn: () => plansAPI.list(Number(projectId)),
  });

  const { data: deliveryGroups } = useQuery({
    queryKey: ['deliveryGroups', projectId],
    queryFn: () => deliveryGroupsAPI.list(Number(projectId)),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file }: { file: File }) => skusAPI.bulkCreate(Number(projectId), file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
    },
  });

  const createContainerMutation = useMutation({
    mutationFn: (data: any) => containersAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectId] });
      setShowContainerModal(false);
      setContainerForm({
        name: '', inner_length: '', inner_width: '', inner_height: '',
        door_width: '', door_height: '', max_weight: '',
        front_axle_limit: '', rear_axle_limit: '',
      });
    },
  });

  const createPlanMutation = useMutation({
    mutationFn: (data: any) => plansAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans', projectId] });
      setShowPlanModal(false);
      setPlanForm({ name: '', container_id: '' });
    },
  });

  const deleteSKUMutation = useMutation({
    mutationFn: (id: number) => skusAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
    },
  });

  const deleteContainerMutation = useMutation({
    mutationFn: (id: number) => containersAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectId] });
    },
  });

  const deletePlanMutation = useMutation({
    mutationFn: (id: number) => plansAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans', projectId] });
    },
  });

  const createSKUMutation = useMutation({
    mutationFn: (data: any) => skusAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
      setShowSKUModal(false);
      setEditingSKU(null);
      setSkuForm({
        name: '', length: '', width: '', height: '', weight: '',
        quantity: '1', fragile: false, max_stack: '999', delivery_group_id: '',
      });
    },
  });

  const updateSKUMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => skusAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
      setShowSKUModal(false);
      setEditingSKU(null);
      setSkuForm({
        name: '', length: '', width: '', height: '', weight: '',
        quantity: '1', fragile: false, max_stack: '999', delivery_group_id: '',
      });
    },
  });

  const createGroupMutation = useMutation({
    mutationFn: (data: any) => deliveryGroupsAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveryGroups', projectId] });
      setShowGroupModal(false);
      setGroupForm({ name: '', color: '#3B82F6', delivery_order: '1' });
      setEditingGroup(null);
    },
  });

  const updateGroupMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => deliveryGroupsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveryGroups', projectId] });
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
      setShowGroupModal(false);
      setGroupForm({ name: '', color: '#3B82F6', delivery_order: '1' });
      setEditingGroup(null);
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: (id: number) => deliveryGroupsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deliveryGroups', projectId] });
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
    },
  });

  const updateSKUGroupMutation = useMutation({
    mutationFn: ({ skuId, groupId }: { skuId: number; groupId: number | null }) => 
      groupId ? deliveryGroupsAPI.assignSKUs(groupId, [skuId]) : skusAPI.update(skuId, { delivery_group_id: null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skus', projectId] });
      queryClient.invalidateQueries({ queryKey: ['deliveryGroups', projectId] });
    },
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate({ file });
    }
  };

  const handleCreateContainer = (e: React.FormEvent) => {
    e.preventDefault();
    createContainerMutation.mutate({
      project_id: Number(projectId),
      name: containerForm.name,
      inner_length: parseFloat(containerForm.inner_length),
      inner_width: parseFloat(containerForm.inner_width),
      inner_height: parseFloat(containerForm.inner_height),
      door_width: parseFloat(containerForm.door_width),
      door_height: parseFloat(containerForm.door_height),
      max_weight: parseFloat(containerForm.max_weight),
      front_axle_limit: containerForm.front_axle_limit ? parseFloat(containerForm.front_axle_limit) : null,
      rear_axle_limit: containerForm.rear_axle_limit ? parseFloat(containerForm.rear_axle_limit) : null,
      obstacles: [],
    });
  };

  const handleCreatePlan = (e: React.FormEvent) => {
    e.preventDefault();
    createPlanMutation.mutate({
      project_id: Number(projectId),
      name: planForm.name,
      container_id: Number(planForm.container_id),
      solver_mode: 'OPTIMAL',  // Always use optimal solver
    });
  };

  const handleCreateSKU = (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      project_id: Number(projectId),
      name: skuForm.name,
      length: parseFloat(skuForm.length),
      width: parseFloat(skuForm.width),
      height: parseFloat(skuForm.height),
      weight: parseFloat(skuForm.weight),
      quantity: parseInt(skuForm.quantity),
      fragile: skuForm.fragile,
      max_stack: parseInt(skuForm.max_stack),
      delivery_group_id: skuForm.delivery_group_id ? Number(skuForm.delivery_group_id) : null,
    };

    if (editingSKU) {
      updateSKUMutation.mutate({ id: editingSKU.id, data });
    } else {
      createSKUMutation.mutate(data);
    }
  };

  const openEditSKU = (sku: SKU) => {
    setEditingSKU(sku);
    setSkuForm({
      name: sku.name,
      length: String(sku.length),
      width: String(sku.width),
      height: String(sku.height),
      weight: String(sku.weight),
      quantity: String(sku.quantity),
      fragile: sku.fragile || false,
      max_stack: String(sku.max_stack || 999),
      delivery_group_id: sku.delivery_group_id ? String(sku.delivery_group_id) : '',
    });
    setShowSKUModal(true);
  };

  const handleCreateOrUpdateGroup = (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      project_id: Number(projectId),
      name: groupForm.name,
      color: groupForm.color,
      delivery_order: parseInt(groupForm.delivery_order),
    };
    
    if (editingGroup) {
      updateGroupMutation.mutate({ id: editingGroup.id, data });
    } else {
      createGroupMutation.mutate(data);
    }
  };

  const openEditGroup = (group: DeliveryGroup) => {
    setEditingGroup(group);
    setGroupForm({
      name: group.name,
      color: group.color || '#3B82F6',
      delivery_order: String(group.delivery_order),
    });
    setShowGroupModal(true);
  };

  const getGroupForSKU = (skuGroupId: number | null | undefined): DeliveryGroup | undefined => {
    if (!skuGroupId || !deliveryGroups) return undefined;
    return deliveryGroups.find((g: DeliveryGroup) => g.id === skuGroupId);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-800 mb-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </button>
          <h1 className="text-2xl font-bold text-gray-800">{project?.name}</h1>
          {project?.description && (
            <p className="text-gray-600 mt-1">{project.description}</p>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs */}
        <div className="bg-white rounded-lg shadow mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('skus')}
                className={`py-4 px-6 border-b-2 font-medium text-sm ${
                  activeTab === 'skus'
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                SKUs ({skus?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab('groups')}
                className={`py-4 px-6 border-b-2 font-medium text-sm ${
                  activeTab === 'groups'
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Groups ({deliveryGroups?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab('containers')}
                className={`py-4 px-6 border-b-2 font-medium text-sm ${
                  activeTab === 'containers'
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Containers ({containers?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab('plans')}
                className={`py-4 px-6 border-b-2 font-medium text-sm ${
                  activeTab === 'plans'
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Plans ({plans?.length || 0})
              </button>
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'skus' && (
              <div>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold">SKU List</h3>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditingSKU(null);
                        setSkuForm({
                          name: '', length: '', width: '', height: '', weight: '',
                          quantity: '1', fragile: false, max_stack: '999', delivery_group_id: '',
                        });
                        setShowSKUModal(true);
                      }}
                      className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                    >
                      <Plus className="w-4 h-4" />
                      Add SKU
                    </button>
                    <label className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 cursor-pointer">
                      <Upload className="w-4 h-4" />
                      Import CSV
                      <input
                        type="file"
                        accept=".csv"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                    </label>
                  </div>
                </div>

                {skus && skus.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Dimensions (L×W×H)</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Weight</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Qty</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Fragile</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Group</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {skus.map((sku: SKU) => {
                          const group = getGroupForSKU(sku.delivery_group_id);
                          return (
                            <tr key={sku.id}>
                              <td className="px-4 py-3 text-sm text-gray-900">{sku.name}</td>
                              <td className="px-4 py-3 text-sm text-gray-600">
                                {sku.length} × {sku.width} × {sku.height} cm
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-600">{sku.weight} kg</td>
                              <td className="px-4 py-3 text-sm text-gray-600">{sku.quantity}</td>
                              <td className="px-4 py-3 text-sm">
                                {sku.fragile ? (
                                  <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Yes</span>
                                ) : (
                                  <span className="px-2 py-1 text-xs bg-gray-100 text-gray-800 rounded">No</span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm">
                                <select
                                  value={sku.delivery_group_id || ''}
                                  onChange={(e) => updateSKUGroupMutation.mutate({
                                    skuId: sku.id,
                                    groupId: e.target.value ? Number(e.target.value) : null
                                  })}
                                  className="text-sm border border-gray-300 rounded px-2 py-1"
                                  style={group ? { borderColor: group.color, borderWidth: '2px' } : {}}
                                >
                                  <option value="">No Group</option>
                                  {deliveryGroups?.map((g: DeliveryGroup) => (
                                    <option key={g.id} value={g.id}>{g.name} (#{g.delivery_order})</option>
                                  ))}
                                </select>
                              </td>
                              <td className="px-4 py-3 text-sm">
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => openEditSKU(sku)}
                                    className="text-blue-600 hover:text-blue-800"
                                    title="Edit SKU"
                                  >
                                    <Edit2 className="w-4 h-4" />
                                  </button>
                                  <button
                                    onClick={() => deleteSKUMutation.mutate(sku.id)}
                                    className="text-red-600 hover:text-red-800"
                                    title="Delete SKU"
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <Package className="w-12 h-12 mx-auto mb-4 text-gray-400" />
                    No SKUs yet. Add SKUs manually or import a CSV file.
                  </div>
                )}
              </div>
            )}

            {activeTab === 'groups' && (
              <div>
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h3 className="text-lg font-semibold">Delivery Groups</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      Group SKUs by delivery location. Lower delivery order = unloaded first = loaded last (near door).
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setEditingGroup(null);
                      setGroupForm({ name: '', color: '#3B82F6', delivery_order: String((deliveryGroups?.length || 0) + 1) });
                      setShowGroupModal(true);
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                  >
                    <Plus className="w-4 h-4" />
                    Add Group
                  </button>
                </div>

                {deliveryGroups && deliveryGroups.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {deliveryGroups
                      .sort((a: DeliveryGroup, b: DeliveryGroup) => a.delivery_order - b.delivery_order)
                      .map((group: DeliveryGroup) => {
                        const groupSkus = skus?.filter((s: SKU) => s.delivery_group_id === group.id) || [];
                        return (
                          <div
                            key={group.id}
                            className="border-2 rounded-lg p-4 relative"
                            style={{ borderColor: group.color || '#E5E7EB' }}
                          >
                            <div className="flex justify-between items-start mb-3">
                              <div className="flex items-center gap-2">
                                <div
                                  className="w-4 h-4 rounded-full"
                                  style={{ backgroundColor: group.color || '#3B82F6' }}
                                />
                                <h4 className="font-semibold">{group.name}</h4>
                              </div>
                              <div className="flex gap-1">
                                <button
                                  onClick={() => openEditGroup(group)}
                                  className="text-gray-600 hover:text-gray-800 p-1"
                                  title="Edit Group"
                                >
                                  <Edit2 className="w-4 h-4" />
                                </button>
                                <button
                                  onClick={() => deleteGroupMutation.mutate(group.id)}
                                  className="text-red-600 hover:text-red-800 p-1"
                                  title="Delete Group"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                            <div className="space-y-2">
                              <div className="flex items-center gap-2 text-sm">
                                <Tag className="w-4 h-4 text-gray-400" />
                                <span className="text-gray-600">
                                  Delivery Order: <strong>#{group.delivery_order}</strong>
                                </span>
                              </div>
                              <div className="flex items-center gap-2 text-sm">
                                <Package className="w-4 h-4 text-gray-400" />
                                <span className="text-gray-600">
                                  {groupSkus.length} SKU{groupSkus.length !== 1 ? 's' : ''} assigned
                                </span>
                              </div>
                              {groupSkus.length > 0 && (
                                <div className="mt-2 pt-2 border-t border-gray-200">
                                  <p className="text-xs text-gray-500 mb-1">Assigned SKUs:</p>
                                  <div className="flex flex-wrap gap-1">
                                    {groupSkus.slice(0, 5).map((sku: SKU) => (
                                      <span key={sku.id} className="px-2 py-0.5 text-xs bg-gray-100 rounded">
                                        {sku.name}
                                      </span>
                                    ))}
                                    {groupSkus.length > 5 && (
                                      <span className="px-2 py-0.5 text-xs bg-gray-100 rounded">
                                        +{groupSkus.length - 5} more
                                      </span>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <Tag className="w-12 h-12 mx-auto mb-4 text-gray-400" />
                    No delivery groups yet. Create groups to organize SKUs by delivery location.
                  </div>
                )}
              </div>
            )}

            {activeTab === 'containers' && (
              <div>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold">Containers</h3>
                  <button
                    onClick={() => setShowContainerModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                  >
                    <Plus className="w-4 h-4" />
                    Add Container
                  </button>
                </div>

                {containers && containers.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {containers.map((container: any) => (
                      <div key={container.id} className="border rounded-lg p-4 relative">
                        <button
                          onClick={() => deleteContainerMutation.mutate(container.id)}
                          className="absolute top-2 right-2 text-red-600 hover:text-red-800"
                          title="Delete Container"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                        <h4 className="font-semibold mb-2">{container.name}</h4>
                        <div className="text-sm text-gray-600 space-y-1">
                          <div>Dimensions: {container.inner_length} × {container.inner_width} × {container.inner_height} cm</div>
                          <div>Door: {container.door_width} × {container.door_height} cm</div>
                          <div>Max Weight: {container.max_weight} kg</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    No containers yet. Add a container to start planning.
                  </div>
                )}
              </div>
            )}

            {activeTab === 'plans' && (
              <div>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold">Loading Plans</h3>
                  <button
                    onClick={() => setShowPlanModal(true)}
                    disabled={!containers || containers.length === 0}
                    className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    title={!containers || containers.length === 0 ? 'Add a container first' : 'Create new plan'}
                  >
                    <Play className="w-4 h-4" />
                    Create Plan
                  </button>
                </div>

                {plans && plans.length > 0 ? (
                  <div className="space-y-4">
                    {plans.map((plan: any) => (
                      <div
                        key={plan.id}
                        className="border rounded-lg p-4 hover:shadow-md transition-shadow relative"
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deletePlanMutation.mutate(plan.id);
                          }}
                          className="absolute top-2 right-2 text-red-600 hover:text-red-800"
                          title="Delete Plan"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                        <div 
                          onClick={() => navigate(`/plan/${plan.id}`)}
                          className="cursor-pointer"
                        >
                          <div className="flex justify-between items-start pr-8">
                            <div>
                              <h4 className="font-semibold">{plan.name}</h4>
                              <div className="text-sm text-gray-600 mt-1">
                                Status: <span className={`font-medium ${
                                  plan.status === 'DONE' ? 'text-green-600' :
                                  plan.status === 'RUNNING' ? 'text-blue-600' :
                                  plan.status === 'FAILED' ? 'text-red-600' :
                                  'text-gray-600'
                                }`}>{plan.status}</span>
                              </div>
                            </div>
                            {plan.status === 'DONE' && (
                              <div className="text-right">
                                <div className="text-sm font-medium text-primary-600">
                                  {plan.utilization_pct.toFixed(1)}% utilized
                                </div>
                                <div className="text-xs text-gray-500">
                                  {plan.items_placed}/{plan.items_total} items
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    No plans yet. Create a plan to optimize your load.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Container Creation Modal */}
      {showContainerModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="text-xl font-semibold mb-4">Add Container</h3>
            <form onSubmit={handleCreateContainer}>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Container Name</label>
                  <input
                    type="text"
                    value={containerForm.name}
                    onChange={(e) => setContainerForm({ ...containerForm, name: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="e.g., 40ft Container"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Length (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.inner_length}
                    onChange={(e) => setContainerForm({ ...containerForm, inner_length: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Width (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.inner_width}
                    onChange={(e) => setContainerForm({ ...containerForm, inner_width: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Height (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.inner_height}
                    onChange={(e) => setContainerForm({ ...containerForm, inner_height: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Weight (kg)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.max_weight}
                    onChange={(e) => setContainerForm({ ...containerForm, max_weight: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Door Width (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.door_width}
                    onChange={(e) => setContainerForm({ ...containerForm, door_width: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Door Height (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.door_height}
                    onChange={(e) => setContainerForm({ ...containerForm, door_height: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Front Axle Limit (kg) - Optional</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.front_axle_limit}
                    onChange={(e) => setContainerForm({ ...containerForm, front_axle_limit: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Rear Axle Limit (kg) - Optional</label>
                  <input
                    type="number"
                    step="0.1"
                    value={containerForm.rear_axle_limit}
                    onChange={(e) => setContainerForm({ ...containerForm, rear_axle_limit: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => setShowContainerModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createContainerMutation.isPending}
                  className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {createContainerMutation.isPending ? 'Creating...' : 'Create Container'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Plan Creation Modal */}
      {showPlanModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <h3 className="text-xl font-semibold mb-4">Create Loading Plan</h3>
            <form onSubmit={handleCreatePlan}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Plan Name</label>
                  <input
                    type="text"
                    value={planForm.name}
                    onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="e.g., Shipment #123"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Select Container</label>
                  <select
                    value={planForm.container_id}
                    onChange={(e) => setPlanForm({ ...planForm, container_id: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  >
                    <option value="">Choose a container...</option>
                    {containers?.map((container: any) => (
                      <option key={container.id} value={container.id}>
                        {container.name} ({container.inner_length}×{container.inner_width}×{container.inner_height} cm)
                      </option>
                    ))}
                  </select>
                </div>
                
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-sm text-blue-800 font-medium">🔬 Optimal Solver</p>
                  <p className="text-xs text-blue-600 mt-1">
                    Exhaustive 5-phase optimization for best possible solution.
                    Time varies based on number of boxes (1-10 minutes).
                  </p>
                </div>
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => setShowPlanModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createPlanMutation.isPending}
                  className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {createPlanMutation.isPending ? 'Creating...' : 'Create Plan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SKU Creation/Edit Modal */}
      {showSKUModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="text-xl font-semibold mb-4">{editingSKU ? 'Edit SKU' : 'Add SKU'}</h3>
            <form onSubmit={handleCreateSKU}>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">SKU Name</label>
                  <input
                    type="text"
                    value={skuForm.name}
                    onChange={(e) => setSkuForm({ ...skuForm, name: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="e.g., Product A Box"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Length (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={skuForm.length}
                    onChange={(e) => setSkuForm({ ...skuForm, length: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Width (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={skuForm.width}
                    onChange={(e) => setSkuForm({ ...skuForm, width: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Height (cm)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={skuForm.height}
                    onChange={(e) => setSkuForm({ ...skuForm, height: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Weight (kg)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={skuForm.weight}
                    onChange={(e) => setSkuForm({ ...skuForm, weight: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
                  <input
                    type="number"
                    step="1"
                    min="1"
                    value={skuForm.quantity}
                    onChange={(e) => setSkuForm({ ...skuForm, quantity: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Group</label>
                  <select
                    value={skuForm.delivery_group_id}
                    onChange={(e) => setSkuForm({ ...skuForm, delivery_group_id: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">No Group</option>
                    {deliveryGroups?.map((g: DeliveryGroup) => (
                      <option key={g.id} value={g.id}>{g.name} (Delivery #{g.delivery_order})</option>
                    ))}
                  </select>
                </div>
                
                <div className="flex items-center gap-4 col-span-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={skuForm.fragile}
                      onChange={(e) => setSkuForm({ ...skuForm, fragile: e.target.checked })}
                      className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm text-gray-700">Fragile (place on top only)</span>
                  </label>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Stack</label>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    value={skuForm.max_stack}
                    onChange={(e) => setSkuForm({ ...skuForm, max_stack: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="999 = unlimited"
                  />
                  <p className="text-xs text-gray-500 mt-1">Max items that can be stacked on top (0 = none)</p>
                </div>
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setShowSKUModal(false);
                    setEditingSKU(null);
                    setSkuForm({
                      name: '', length: '', width: '', height: '', weight: '',
                      quantity: '1', fragile: false, max_stack: '999', delivery_group_id: '',
                    });
                  }}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSKUMutation.isPending || updateSKUMutation.isPending}
                  className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {(createSKUMutation.isPending || updateSKUMutation.isPending)
                    ? 'Saving...'
                    : editingSKU ? 'Update SKU' : 'Add SKU'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Group Creation/Edit Modal */}
      {showGroupModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <h3 className="text-xl font-semibold mb-4">
              {editingGroup ? 'Edit Delivery Group' : 'Create Delivery Group'}
            </h3>
            <form onSubmit={handleCreateOrUpdateGroup}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Group Name</label>
                  <input
                    type="text"
                    value={groupForm.name}
                    onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="e.g., Location A - Downtown"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Order</label>
                  <input
                    type="number"
                    step="1"
                    min="1"
                    value={groupForm.delivery_order}
                    onChange={(e) => setGroupForm({ ...groupForm, delivery_order: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    required
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Lower number = first delivery stop. First delivery items will be loaded last (near door).
                  </p>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Color</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={groupForm.color}
                      onChange={(e) => setGroupForm({ ...groupForm, color: e.target.value })}
                      className="w-12 h-10 rounded border border-gray-300 cursor-pointer"
                    />
                    <div className="flex gap-2">
                      {['#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6', '#EC4899'].map((c) => (
                        <button
                          key={c}
                          type="button"
                          onClick={() => setGroupForm({ ...groupForm, color: c })}
                          className={`w-8 h-8 rounded-full border-2 ${groupForm.color === c ? 'border-gray-800' : 'border-transparent'}`}
                          style={{ backgroundColor: c }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setShowGroupModal(false);
                    setEditingGroup(null);
                    setGroupForm({ name: '', color: '#3B82F6', delivery_order: '1' });
                  }}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createGroupMutation.isPending || updateGroupMutation.isPending}
                  className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {(createGroupMutation.isPending || updateGroupMutation.isPending) 
                    ? 'Saving...' 
                    : editingGroup ? 'Update Group' : 'Create Group'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectDetail;
