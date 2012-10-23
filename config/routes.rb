Blaha::Application.routes.draw do
  resources :taggings

  resources :tags

  resources :links

  devise_for :users

  get "welcome/index"

  root :to => 'welcome#index'
end
