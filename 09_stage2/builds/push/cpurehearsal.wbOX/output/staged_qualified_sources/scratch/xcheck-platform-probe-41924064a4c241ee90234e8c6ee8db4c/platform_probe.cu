#include <cuda_runtime.h>
#include <cstdio>
int main() {
  int count = 0, driver = 0, runtime = 0;
  if (cudaGetDeviceCount(&count) != cudaSuccess || count < 1) return 1;
  cudaDeviceProp p{};
  if (cudaGetDeviceProperties(&p, 0) != cudaSuccess || p.major < 1) return 1;
  if (cudaDriverGetVersion(&driver) != cudaSuccess) return 1;
  if (cudaRuntimeGetVersion(&runtime) != cudaSuccess) return 1;
  std::printf("{\"gpu_name\":\"%s\",\"compute_capability\":\"%d.%d\","
              "\"cuda_driver_version\":\"%d\",\"cuda_runtime_version\":\"%d\"}\n",
              p.name, p.major, p.minor, driver, runtime);
  return 0;
}
