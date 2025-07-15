for i in {1..10}; do
# source folder:
#   if [ "$i" -eq 7 ]; then
#     continue
#   fi
  target=~/workspace/${i}ORFS
  mkdir -p "$target/.vscode"
  cp ~/workspace/7ORFS/.vscode/settings.json "$target/.vscode/settings.json"
  sed -i "s|/home/aberndt/workspace/7ORFS|/home/aberndt/workspace/${i}ORFS|g" "$target/.vscode/settings.json"
done
