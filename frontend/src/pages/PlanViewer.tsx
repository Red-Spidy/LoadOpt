import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { plansAPI, skusAPI, containersAPI } from '@/services/api';
import { ArrowLeft, Download } from 'lucide-react';
import Viewer3D from '@/components/Viewer3D';
import type { SKU } from '@/types';

const PlanViewer: React.FC = () => {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();

  const handleExportCSV = async () => {
    try {
      const blob = await plansAPI.exportCSV(Number(planId));
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `plan_${planId}_export.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  const { data: plan, isLoading } = useQuery({
    queryKey: ['plan', planId],
    queryFn: () => plansAPI.get(Number(planId)),
    refetchInterval: (query) => {
      // Refetch every 2 seconds if plan is running
      return query?.state?.data?.status === 'RUNNING' ? 2000 : false;
    },
  });

  const { data: skus } = useQuery({
    queryKey: ['skus', plan?.project_id],
    queryFn: () => skusAPI.list(plan!.project_id),
    enabled: !!plan?.project_id,
  });

  const { data: container } = useQuery({
    queryKey: ['container', plan?.container_id],
    queryFn: () => containersAPI.get(plan!.container_id),
    enabled: !!plan?.container_id,
  });

  if (isLoading || !plan) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm z-10">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(`/project/${plan.project_id}`)}
              className="flex items-center gap-2 text-gray-600 hover:text-gray-800"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <div>
              <h1 className="text-xl font-bold text-gray-800">{plan.name}</h1>
              <div className="text-sm text-gray-600">
                Status: <span className={`font-medium ${
                  plan.status === 'DONE' ? 'text-green-600' :
                  plan.status === 'RUNNING' ? 'text-blue-600' :
                  plan.status === 'FAILED' ? 'text-red-600' :
                  'text-gray-600'
                }`}>{plan.status}</span>
              </div>
            </div>
          </div>

          {plan.status === 'DONE' && (
            <div className="flex gap-6 items-center">
              <div className="text-center">
                <div className="text-2xl font-bold text-primary-600">
                  {plan.utilization_pct.toFixed(1)}%
                </div>
                <div className="text-xs text-gray-500">Utilization</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-800">
                  {plan.items_placed}/{plan.items_total}
                </div>
                <div className="text-xs text-gray-500">Items Placed</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-800">
                  {plan.total_weight.toFixed(0)} kg
                </div>
                <div className="text-xs text-gray-500">Total Weight</div>
              </div>
              <button
                onClick={handleExportCSV}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* 3D Viewer */}
        <div className="flex-1 relative">
          {plan.status === 'RUNNING' ? (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
              <div className="text-center">
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary-600 mx-auto mb-4"></div>
                <p className="text-white text-lg">Optimizing load plan...</p>
              </div>
            </div>
          ) : plan.status === 'FAILED' ? (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
              <div className="text-center text-white">
                <p className="text-xl mb-2">Optimization Failed</p>
                {plan.validation_errors.map((error: string, idx: number) => (
                  <p key={idx} className="text-sm text-red-400">{error}</p>
                ))}
              </div>
            </div>
          ) : plan.placements && plan.placements.length > 0 && skus && container ? (
            <Viewer3D
              placements={plan.placements}
              skus={skus}
              container={container}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900 text-white">
              <p>No placements to display</p>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="w-96 bg-white shadow-lg overflow-y-auto p-4">
          <h3 className="font-semibold text-lg mb-4">Load Plan Details</h3>

          {plan.status === 'DONE' && plan.placements && skus && (
            <div className="space-y-4">
              {/* SKU Breakdown with Colors */}
              <div className="bg-gray-50 rounded-lg p-3">
                <h4 className="font-medium text-sm mb-3">SKU Breakdown</h4>
                <div className="space-y-2">
                  {(() => {
                    // Generate the same bright colors as Viewer3D
                    const brightColors = [
                      '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
                      '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B88B', '#ABEBC6',
                      '#FAD7A0', '#D7BDE2', '#A9DFBF', '#F9E79F', '#AED6F1',
                      '#FADBD8', '#D5F4E6', '#FCF3CF', '#E8DAEF', '#EDBB99'
                    ];
                    const skuColors: Record<number, string> = {};
                    skus.forEach((sku: SKU, index: number) => {
                      skuColors[sku.id] = brightColors[index % brightColors.length];
                    });

                    // Count placements by SKU
                    const skuCounts: Record<number, number> = {};
                    plan.placements.forEach((placement: any) => {
                      skuCounts[placement.sku_id] = (skuCounts[placement.sku_id] || 0) + 1;
                    });

                    return skus
                      .filter((sku: SKU) => skuCounts[sku.id] > 0)
                      .map((sku: SKU) => (
                        <div key={sku.id} className="flex items-start gap-2 text-sm border-b border-gray-200 pb-2 last:border-0">
                          <div
                            className="w-6 h-6 rounded flex-shrink-0 mt-0.5 border border-gray-300"
                            style={{ backgroundColor: skuColors[sku.id] }}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-gray-900 truncate">{sku.name}</div>
                            <div className="text-xs text-gray-600">
                              Qty: <span className="font-semibold">{skuCounts[sku.id]}</span> of {sku.quantity}
                            </div>
                            {sku.delivery_group_id && (
                              <div className="text-xs text-blue-600 mt-0.5">
                                📍 Delivery Group #{sku.delivery_group_id}
                              </div>
                            )}
                            <div className="text-xs text-gray-500 mt-0.5">
                              {sku.length}×{sku.width}×{sku.height} cm, {sku.weight} kg
                            </div>
                          </div>
                        </div>
                      ));
                  })()}
                </div>
              </div>

              {plan.weight_distribution && (
                <>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <h4 className="font-medium text-sm mb-2">Weight Distribution</h4>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Front Axle:</span>
                        <span className="font-medium">{plan.weight_distribution.front_axle.toFixed(1)} kg</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Rear Axle:</span>
                        <span className="font-medium">{plan.weight_distribution.rear_axle.toFixed(1)} kg</span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gray-50 rounded-lg p-3">
                    <h4 className="font-medium text-sm mb-2">Center of Gravity</h4>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">X:</span>
                        <span className="font-medium">{plan.weight_distribution.center_of_gravity.x.toFixed(1)} cm</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Y:</span>
                        <span className="font-medium">{plan.weight_distribution.center_of_gravity.y.toFixed(1)} cm</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Z:</span>
                        <span className="font-medium">{plan.weight_distribution.center_of_gravity.z.toFixed(1)} cm</span>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {!plan.is_valid && plan.validation_errors.length > 0 && (
                <div className="bg-red-50 rounded-lg p-3">
                  <h4 className="font-medium text-sm text-red-800 mb-2">Validation Errors</h4>
                  <ul className="space-y-1 text-sm text-red-600">
                    {plan.validation_errors.map((error: string, idx: number) => (
                      <li key={idx}>• {error}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PlanViewer;
