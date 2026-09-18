#!/usr/bin/env bash
#
# Make locally built images visible to the cluster.
#
# Each local Kubernetes distribution handles this differently, and getting it
# wrong is the most common cause of ImagePullBackOff with imagePullPolicy:
# IfNotPresent. Docker Desktop shares the daemon, so nothing is needed; kind and
# minikube keep their own image stores and need an explicit load.
set -euo pipefail

IMAGES=("cerebro-api:0.1.0" "cerebro-web:0.1.0")
context="$(kubectl config current-context 2>/dev/null || echo unknown)"

echo "Cluster context: ${context}"

case "${context}" in
  kind-*)
    cluster="${context#kind-}"
    for image in "${IMAGES[@]}"; do
      echo "  kind load docker-image ${image} --name ${cluster}"
      kind load docker-image "${image}" --name "${cluster}"
    done
    ;;
  minikube)
    for image in "${IMAGES[@]}"; do
      echo "  minikube image load ${image}"
      minikube image load "${image}"
    done
    ;;
  docker-desktop|rancher-desktop)
    echo "  Shares the local Docker daemon — no load needed."
    ;;
  *)
    echo "  Unrecognised context '${context}'."
    echo "  If pods report ImagePullBackOff, the cluster cannot see locally"
    echo "  built images. Load them the way your distribution expects, or push"
    echo "  them to a registry the cluster can reach and update the image names"
    echo "  in k8s/20-api.yaml and k8s/30-web.yaml."
    ;;
esac
